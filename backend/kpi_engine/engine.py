"""Deterministic KPI calculation service.

Rules enforced here (each one has a test):
  * ratio of sums, summed with math.fsum -> identical result whatever the row order;
  * rows with missing / non-finite / out-of-range inputs are excluded from numerator AND
    denominator and counted with a reason; nothing is imputed;
  * value is None (never 0 / inf / NaN) when the denominator is <= 0 or no valid row remains;
  * unit problems (fraction-vs-percent, mixed currency) -> status invalid_units, no value;
  * targets are evaluated only when supplied with a source; otherwise 'no_target_defined';
  * cross-dataset comparison is refused unless definitions, populations and periods are compatible.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from .contract import KPIResult, Status, TargetSpec, TrendPoint, TrendResult
from .datasets import DATASETS, PreparedDataset, DatasetSpec, load_raw, prepare
from .registry import REGISTRY, REGISTRY_VERSION, TARGETS, KPIDefinition

FREQS = {"day": "D", "week": "W-SUN", "month": "M", "quarter": "Q"}
_ALLOWED_FREQS = {"day": ("day", "week", "month", "quarter"), "month": ("month", "quarter")}
_MISSING_GROUP = "(missing)"


class KPIEngineError(ValueError):
    """Bad request: unknown KPI/dataset/filter/frequency, invalid date range."""


@dataclass
class _Calc:
    value: float | None
    status: Status
    n_input: int
    n_used: int
    reasons: dict[str, int]
    num: float | None
    den: float | None
    used: pd.DataFrame


def _to_date(v: Any, name: str) -> pd.Timestamp | None:
    if v is None or v == "":
        return None
    try:
        ts = pd.Timestamp(v)
    except (ValueError, TypeError) as exc:
        raise KPIEngineError(f"{name} is not a valid date: {v!r}") from exc
    if pd.isna(ts):
        raise KPIEngineError(f"{name} is not a valid date: {v!r}")
    return ts.tz_localize(None) if ts.tzinfo else ts


class KPIEngine:
    def __init__(self, data_dir: str | Path | None = None, frames: Mapping[str, pd.DataFrame] | None = None):
        self._data_dir = Path(data_dir) if data_dir else None
        self._frames = dict(frames or {})
        self._cache: dict[tuple[str, str], PreparedDataset] = {}

    # ------------------------------------------------------------------ data access
    def dataset(self, dataset_id: str, conflict_policy: str | None = None) -> PreparedDataset:
        spec = self._spec(dataset_id)
        policy = conflict_policy or spec.default_conflict_policy
        key = (dataset_id, policy)
        if key not in self._cache:
            if dataset_id in self._frames:
                raw = self._frames[dataset_id]
            elif self._data_dir is not None:
                raw = load_raw(spec, self._data_dir)
            else:
                raise KPIEngineError(f"no data source configured for dataset '{dataset_id}'")
            self._cache[key] = prepare(spec, raw, policy)
        return self._cache[key]

    @staticmethod
    def _spec(dataset_id: str) -> DatasetSpec:
        if dataset_id not in DATASETS:
            raise KPIEngineError(f"unknown dataset '{dataset_id}'")
        return DATASETS[dataset_id]

    @staticmethod
    def _kpi(key: str, dataset_id: str) -> KPIDefinition:
        if key not in REGISTRY:
            raise KPIEngineError(f"unknown KPI key '{key}'")
        d = REGISTRY[key]
        if dataset_id not in d.datasets:
            raise KPIEngineError(f"KPI '{key}' is not defined for dataset '{dataset_id}' (valid: {', '.join(d.datasets)})")
        return d

    # ------------------------------------------------------------------ selection
    def _select(self, prep: PreparedDataset, date_from: Any, date_to: Any, filters: Mapping[str, Any] | None) -> pd.DataFrame:
        spec, df = prep.spec, prep.df
        d_from, d_to = _to_date(date_from, "date_from"), _to_date(date_to, "date_to")
        if d_from is not None and d_to is not None and d_from > d_to:
            raise KPIEngineError("date_from must be on or before date_to")
        if spec.date_grain == "month":
            per = df["date"].dt.to_period("M")
            if d_from is not None:
                df = df[per >= d_from.to_period("M")]
                per = df["date"].dt.to_period("M")
            if d_to is not None:
                df = df[per <= d_to.to_period("M")]
        else:
            day = df["date"].dt.normalize()
            if d_from is not None:
                df = df[day >= d_from.normalize()]
                day = df["date"].dt.normalize()
            if d_to is not None:
                df = df[day <= d_to.normalize()]
        for col, wanted in (filters or {}).items():
            if col not in spec.group_columns:
                raise KPIEngineError(f"cannot filter '{spec.dataset_id}' by '{col}' (allowed: {', '.join(spec.group_columns)})")
            vals = [wanted] if isinstance(wanted, (str, int, float)) else list(wanted)
            norm = {str(v).strip().lower() for v in vals}
            have = df[col].astype("object").map(lambda v: v.strip().lower() if isinstance(v, str) else None)
            df = df[have.isin(norm)]
        return df

    # ------------------------------------------------------------------ core calculation
    @staticmethod
    def _unit_problem(defn: KPIDefinition, prep: PreparedDataset) -> str | None:
        cs = defn.compute
        used = {cs.numerator, cs.denominator, *cs.required}
        for flag, msg in prep.quality.flags.items():
            if flag.startswith("unit_suspect:") and flag.split(":", 1)[1] in used:
                return msg
        if defn.monetary and "mixed_currency" in prep.quality.flags:
            return prep.quality.flags["mixed_currency"]
        return None

    @staticmethod
    def _calc(df: pd.DataFrame, defn: KPIDefinition) -> _Calc:
        cs = defn.compute
        n_input = len(df)
        if n_input == 0:
            return _Calc(None, Status.NO_DATA, 0, 0, {}, None, None, df)
        mask = pd.Series(True, index=df.index)
        reasons: dict[str, int] = {}

        def drop(bad: pd.Series, name: str) -> None:
            nonlocal mask
            bad = bad & mask
            k = int(bad.sum())
            if k:
                reasons[name] = reasons.get(name, 0) + k
                mask = mask & ~bad

        for c in cs.required:
            drop(~np.isfinite(df[c].astype("float64")), f"missing:{c}")
        for c in cs.non_negative:
            drop(df[c] < 0, f"negative:{c}")
        for c in cs.positive:
            drop(df[c] <= 0, f"non_positive:{c}")
        for a, b in cs.at_most:
            drop(df[a] > df[b], f"{a}_exceeds_{b}")
        for c, lo, hi in cs.in_range:
            drop((df[c] < lo) | (df[c] > hi), f"out_of_range:{c}[{lo:g},{hi:g}]")

        used = df[mask]
        n_used = len(used)
        if n_used == 0:
            return _Calc(None, Status.INVALID_DENOMINATOR, n_input, 0, reasons, None, None, used)
        num = math.fsum(used[cs.numerator].astype("float64").tolist())
        den = math.fsum(used[cs.denominator].astype("float64").tolist())
        if not math.isfinite(den) or den <= 0:
            return _Calc(None, Status.INVALID_DENOMINATOR, n_input, n_used, reasons, num, den, used)
        value = num / den * cs.scale
        if not math.isfinite(value):
            return _Calc(None, Status.INVALID_DENOMINATOR, n_input, n_used, reasons, num, den, used)
        return _Calc(value, Status.OK, n_input, n_used, reasons, num, den, used)

    # ------------------------------------------------------------------ result assembly
    def _unit_label(self, defn: KPIDefinition, prep: PreparedDataset) -> str:
        cur = prep.currency or "currency units (not stated in source)"
        return defn.unit_label.replace("{currency}", cur)

    def _warnings(self, defn: KPIDefinition, prep: PreparedDataset, calc: _Calc, group_col: str | None) -> list[str]:
        w = list(prep.quality.warnings())
        if group_col and group_col in prep.spec.group_warnings:
            w.append(prep.spec.group_warnings[group_col])
        if calc.reasons:
            parts = ", ".join(f"{k}: {v}" for k, v in sorted(calc.reasons.items()))
            w.append(f"{sum(calc.reasons.values())} of {calc.n_input} selected rows excluded ({parts})")
        if calc.status == Status.OK and calc.n_used < defn.min_sample:
            w.append(f"low_sample: only {calc.n_used} valid rows (< {defn.min_sample}); treat as indicative")
        if defn.key == "procurement.avg_lead_time_days" and calc.status == Status.OK and "status" in calc.used:
            st = calc.used["status"].astype("object").map(lambda v: v.strip().lower() if isinstance(v, str) else "")
            n = int(st.isin(["cancelled", "pending"]).sum())
            if n:
                w.append(f"{n} of the {calc.n_used} POs used are Cancelled/Pending yet carry a delivery date "
                         f"(source inconsistency); filter status=Delivered for a stricter view")
        return w

    @staticmethod
    def _evaluate_target(defn: KPIDefinition, value: float | None, target: TargetSpec | None) -> dict[str, Any]:
        if target is None:
            return {"evidence_type": "target", "status": "no_target_defined", "value": None, "source": None,
                    "note": defn.target_note}
        direction = target.direction or defn.direction
        out: dict[str, Any] = {"evidence_type": "target", "value": target.value, "source": target.source,
                               "direction": direction, "gap_abs": None, "gap_pct": None}
        if value is None:
            out["status"] = "not_evaluable"
            return out
        gap = value - target.value
        out["gap_abs"] = gap
        out["gap_pct"] = (gap / target.value * 100.0) if target.value != 0 else None
        met = value >= target.value if direction == "higher_is_better" else value <= target.value
        out["status"] = "met" if met else "not_met"
        return out

    def _result(self, defn: KPIDefinition, prep: PreparedDataset, calc: _Calc, *, filters: Mapping[str, Any] | None,
                group: dict[str, Any] | None, date_from: Any, date_to: Any, status: Status | None = None,
                extra_warning: str | None = None, target: TargetSpec | None = None) -> KPIResult:
        grain_fmt = "%Y-%m" if prep.spec.date_grain == "month" else "%Y-%m-%d"
        start = calc.used["date"].min().strftime(grain_fmt) if len(calc.used) else None
        end = calc.used["date"].max().strftime(grain_fmt) if len(calc.used) else None
        warnings = self._warnings(defn, prep, calc, next(iter(group)) if group else None)
        if extra_warning:
            warnings.insert(0, extra_warning)
        st = status or calc.status
        value = calc.value if st == Status.OK else None
        return KPIResult(
            key=defn.key, display_name=defn.display_name, unit=defn.unit, unit_label=self._unit_label(defn, prep),
            value=value, status=st, dataset_id=prep.spec.dataset_id, data_source=prep.spec.data_source,
            period={"start": start, "end": end, "grain": prep.spec.date_grain,
                    "requested_from": str(_to_date(date_from, "date_from").date()) if _to_date(date_from, "date_from") is not None else None,
                    "requested_to": str(_to_date(date_to, "date_to").date()) if _to_date(date_to, "date_to") is not None else None,
                    "dataset_declared_period": prep.spec.declared_period},
            filters=dict(filters or {}), group=group, n_rows_input=calc.n_input, n_rows_used=calc.n_used,
            n_rows_excluded=sum(calc.reasons.values()), exclusion_reasons=dict(sorted(calc.reasons.items())),
            numerator_total=calc.num, denominator_total=calc.den, warnings=warnings,
            target=self._evaluate_target(defn, value if st == Status.OK else None, target if target is not None else TARGETS.get(defn.key)),
            registry_version=REGISTRY_VERSION,
        )

    # ------------------------------------------------------------------ public API
    def compute(self, key: str, dataset_id: str, *, date_from: Any = None, date_to: Any = None,
                filters: Mapping[str, Any] | None = None, target: TargetSpec | None = None,
                conflict_policy: str | None = None) -> KPIResult:
        defn = self._kpi(key, dataset_id)
        prep = self.dataset(dataset_id, conflict_policy)
        df = self._select(prep, date_from, date_to, filters)
        problem = self._unit_problem(defn, prep)
        if problem:
            calc = _Calc(None, Status.INVALID_UNITS, len(df), 0, {}, None, None, df.iloc[0:0])
            return self._result(defn, prep, calc, filters=filters, group=None, date_from=date_from, date_to=date_to,
                                status=Status.INVALID_UNITS, extra_warning=problem, target=target)
        return self._result(defn, prep, self._calc(df, defn), filters=filters, group=None,
                            date_from=date_from, date_to=date_to, target=target)

    def compute_grouped(self, key: str, dataset_id: str, group_by: str, *, date_from: Any = None, date_to: Any = None,
                        filters: Mapping[str, Any] | None = None, target: TargetSpec | None = None,
                        conflict_policy: str | None = None) -> list[KPIResult]:
        defn = self._kpi(key, dataset_id)
        prep = self.dataset(dataset_id, conflict_policy)
        if group_by not in prep.spec.group_columns:
            raise KPIEngineError(f"cannot group '{dataset_id}' by '{group_by}' (allowed: {', '.join(prep.spec.group_columns)})")
        df = self._select(prep, date_from, date_to, filters)
        problem = self._unit_problem(defn, prep)
        labels = df[group_by].astype("object").map(lambda v: v if isinstance(v, str) and v else _MISSING_GROUP)
        out: list[KPIResult] = []
        for label in sorted(labels.unique(), key=str):
            sub = df[labels == label]
            if problem:
                calc = _Calc(None, Status.INVALID_UNITS, len(sub), 0, {}, None, None, sub.iloc[0:0])
                out.append(self._result(defn, prep, calc, filters=filters, group={group_by: label}, date_from=date_from,
                                        date_to=date_to, status=Status.INVALID_UNITS, extra_warning=problem, target=target))
            else:
                out.append(self._result(defn, prep, self._calc(sub, defn), filters=filters, group={group_by: label},
                                        date_from=date_from, date_to=date_to, target=target))
        return out

    def trend(self, key: str, dataset_id: str, freq: str, *, date_from: Any = None, date_to: Any = None,
              filters: Mapping[str, Any] | None = None, conflict_policy: str | None = None,
              min_sample: int | None = None) -> TrendResult:
        defn = self._kpi(key, dataset_id)
        prep = self.dataset(dataset_id, conflict_policy)
        spec = prep.spec
        if freq not in FREQS:
            raise KPIEngineError(f"freq must be one of {sorted(FREQS)}")
        if freq not in _ALLOWED_FREQS[spec.date_grain]:
            raise KPIEngineError(f"freq '{freq}' is finer than the {spec.date_grain}-grain data in '{dataset_id}' "
                                 f"(allowed: {', '.join(_ALLOWED_FREQS[spec.date_grain])})")
        floor = defn.min_sample if min_sample is None else int(min_sample)
        df = self._select(prep, date_from, date_to, filters)
        warnings = list(prep.quality.warnings())
        base = dict(key=defn.key, display_name=defn.display_name, unit=defn.unit, unit_label=self._unit_label(defn, prep),
                    dataset_id=dataset_id, data_source=spec.data_source, freq=freq, min_sample=floor,
                    filters=dict(filters or {}), registry_version=REGISTRY_VERSION)
        problem = self._unit_problem(defn, prep)
        if problem:
            return TrendResult(points=[], gap_periods=[], warnings=[problem, *warnings], **base)
        if df.empty:
            return TrendResult(points=[], gap_periods=[], warnings=["no data in the selected window", *warnings], **base)

        pcode = FREQS[freq]
        periods = df["date"].dt.to_period(pcode)
        data_min = df["date"].min()
        data_max = df["date"].max()
        if spec.date_grain == "month":
            data_max = data_max + pd.offsets.MonthEnd(0)
        full = pd.period_range(periods.min(), periods.max(), freq=pcode)

        points: list[TrendPoint] = []
        gaps: list[str] = []
        prev: TrendPoint | None = None
        for i, p in enumerate(full):
            sub = df[periods == p]
            start, end = p.start_time.normalize(), p.end_time.normalize()
            label = _label(p, freq)
            partial = bool((i == 0 and data_min > start) or (i == len(full) - 1 and data_max < end))
            if sub.empty:
                gaps.append(label)
                pt = TrendPoint(label, str(start.date()), str(end.date()), None, Status.NO_DATA, 0, False, partial, None, None,
                                "no records in this period")
                points.append(pt)
                prev = pt
                continue
            calc = self._calc(sub, defn)
            low = calc.n_used < floor
            pt = TrendPoint(label, str(start.date()), str(end.date()), calc.value, calc.status, calc.n_used, low, partial,
                            None, None, None)
            pt.change_note = _change(pt, prev)
            if pt.change_note is None and prev is not None:
                pt.change_abs = pt.value - prev.value  # type: ignore[operator]
                pt.change_pct = (pt.change_abs / prev.value * 100.0) if prev.value not in (None, 0) else None  # type: ignore[operator]
                if pt.change_pct is None:
                    pt.change_note = "previous value is 0: percentage change undefined"
            points.append(pt)
            prev = pt

        evaluable = [p for p in points if p.status == Status.OK and not p.low_sample and not p.partial_period]
        if len(evaluable) < 2:
            warnings.append("fewer than 2 complete, adequately sampled periods: no trend can be stated")
        if gaps:
            warnings.append(f"no data for period(s): {', '.join(gaps)}; changes are not computed across a gap")
        if any(p.partial_period for p in points):
            warnings.append("first/last period only partly covered by the data; its value is not compared with neighbours")
        if prep.spec.group_warnings and filters:
            for col in filters:
                if col in prep.spec.group_warnings:
                    warnings.append(prep.spec.group_warnings[col])
        return TrendResult(points=points, gap_periods=gaps, warnings=warnings, **base)

    # ------------------------------------------------------------------ comparability
    def check_comparability(self, dataset_a: str, dataset_b: str, key: str | None = None) -> dict[str, Any]:
        """Is a cross-dataset comparison of (the same) KPI defensible? Default answer is no."""
        a, b = self._spec(dataset_a), self._spec(dataset_b)
        reasons: list[str] = []
        if key is not None:
            d = REGISTRY.get(key)
            if d is None:
                raise KPIEngineError(f"unknown KPI key '{key}'")
            for s in (a, b):
                if s.dataset_id not in d.datasets:
                    reasons.append(f"KPI '{key}' is not defined for dataset '{s.dataset_id}'")
        if dataset_a != dataset_b:
            if a.data_source != b.data_source:
                reasons.append(f"different data sources ('{a.data_source}' vs '{b.data_source}'): public benchmark and "
                               f"synthetic company records must stay separate")
            if a.entity_scope != b.entity_scope:
                reasons.append(f"different populations ('{a.entity_scope}' vs '{b.entity_scope}')")
            if a.grain != b.grain:
                reasons.append(f"different grain ('{a.grain}' vs '{b.grain}')")
            pa, pb = self._observed(dataset_a), self._observed(dataset_b)
            if pa and pb and (pa[1] < pb[0] or pb[1] < pa[0]):
                reasons.append(f"non-overlapping periods ({pa[0].strftime('%Y-%m')} to {pa[1].strftime('%Y-%m')} vs "
                               f"{pb[0].strftime('%Y-%m')} to {pb[1].strftime('%Y-%m')})")
            elif not (pa and pb):
                reasons.append("observed period unknown (dataset not loaded); cannot verify overlap")
            if a.derived_from_ranges_of == b.dataset_id or b.derived_from_ranges_of == a.dataset_id:
                reasons.append("one dataset's value ranges were copied from the other; a comparison would be circular")
        return {"comparable": not reasons, "dataset_a": dataset_a, "dataset_b": dataset_b, "key": key, "reasons": reasons}

    def _observed(self, dataset_id: str) -> tuple[pd.Timestamp, pd.Timestamp] | None:
        try:
            prep = self.dataset(dataset_id)
        except (KPIEngineError, FileNotFoundError):
            return None
        if prep.df.empty:
            return None
        return prep.df["date"].min(), prep.df["date"].max()


# --------------------------------------------------------------------------- helpers
def _label(p: pd.Period, freq: str) -> str:
    if freq == "day":
        return str(p.start_time.date())
    if freq == "week":
        iso = p.start_time.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    if freq == "month":
        return f"{p.year}-{p.month:02d}"
    return f"{p.year}Q{p.quarter}"


def _change(cur: TrendPoint, prev: TrendPoint | None) -> str | None:
    """Return a reason string when a change cannot be stated, else None."""
    if prev is None:
        return None
    if cur.status != Status.OK:
        return f"value not available ({cur.status.value})"
    if prev.status == Status.NO_DATA:
        return "previous period has no data (gap)"
    if prev.status != Status.OK:
        return f"previous value not available ({prev.status.value})"
    if cur.low_sample or prev.low_sample:
        return "low sample in this or the previous period"
    if cur.partial_period or prev.partial_period:
        return "partly covered period is not comparable with a full one"
    return None
