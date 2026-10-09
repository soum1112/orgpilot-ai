"""
process_kpis.py - OrgPilot AI, Member 2 (Process Intelligence)

Deterministic analytics over a process event log. Python calculates every number;
no LLM is involved. Formulas are documented in KPI_DEFINITIONS.md.

Usage:
    python process_kpis.py            # reads the CSVs next to this file, prints a summary
    from process_kpis import ProcessAnalytics
    pa = ProcessAnalytics.from_files("path/to/folder")
    pa.envelope({"overview": pa.overview()})
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REQUIRED_COLS = ["case_id", "activity", "status", "timestamp"]
OPTIONAL_COLS = ["event_id", "process_id", "case_type", "team", "location", "location_type"]
EVENT_FILE = "process_event_log.csv"
TARGET_FILE = "process_targets.csv"
SEQUENCE_FILE = "process_expected_sequences.csv"

STALLED_AFTER_DAYS = 45   # open case with no event for this long (vs latest event in data) = stalled/abandoned
MIN_STAGE_N = 20          # minimum valid observations before a stage is rated as a bottleneck
HIGH_BREACH = 0.50        # severity thresholds (see KPI_DEFINITIONS.md)
MEDIUM_BREACH = 0.35
COMPARABLE_OK = ("yes", "approximate")
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "unrated": 3}


def _py(o):
    """Make numpy/pandas values JSON-safe (NaN -> None, round floats to 2 dp)."""
    if o is pd.NaT or o is pd.NA:
        return None
    if isinstance(o, dict):
        return {k: _py(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_py(v) for v in o]
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return None if (math.isnan(o) or math.isinf(o)) else round(float(o), 2)
    if isinstance(o, pd.Timestamp):
        return o.isoformat()
    return o


def _mean(s):
    s = pd.Series(s).dropna()
    return float(s.mean()) if len(s) else None


def _median(s):
    s = pd.Series(s).dropna()
    return float(s.median()) if len(s) else None


def _p90(s):
    s = pd.Series(s).dropna()
    return float(s.quantile(0.9)) if len(s) else None


def _rate(num, den):
    return None if not den else float(num) / float(den)


class ProcessAnalytics:
    def __init__(self, events, targets=None, sequences=None,
                 stalled_after_days=STALLED_AFTER_DAYS, min_stage_n=MIN_STAGE_N,
                 source_file=EVENT_FILE):
        self.source_file = source_file
        self.stalled_after_days = stalled_after_days
        self.min_stage_n = min_stage_n
        self.targets = self._prep_targets(targets)
        self.seq = self._prep_sequences(sequences)
        self.has_targets = targets is not None and len(self.targets) > 0
        self.has_sequences = sequences is not None and len(self.seq) > 0
        self.ev, self.quality = self._parse(events)
        self.stages = self._build_stages()
        self.quality["negative_duration_stages"] = (
            int(self.stages["negative_duration"].sum()) if len(self.stages) else 0)
        # Stage timings assume the expected order of activities. Cases whose order deviates are
        # reported under anomalies but excluded from timing statistics (never silently).
        self._ooo, self._skipped, self._unknown = self._sequence_checks()
        self.quality["out_of_order_cases_excluded_from_timing"] = len(self._ooo)
        if self._ooo and len(self.stages):
            m = self.stages["case_id"].isin(self._ooo)
            self.stages.loc[m, ["wait_h", "proc_h", "elapsed_h"]] = np.nan
        self.cases = self._build_cases()

    @classmethod
    def from_files(cls, folder):
        folder = Path(folder)
        ev = pd.read_csv(folder / EVENT_FILE, dtype=str, keep_default_na=False)
        tg = pd.read_csv(folder / TARGET_FILE, dtype=str, keep_default_na=False) if (folder / TARGET_FILE).exists() else None
        sq = pd.read_csv(folder / SEQUENCE_FILE, dtype=str, keep_default_na=False) if (folder / SEQUENCE_FILE).exists() else None
        return cls(ev, tg, sq)

    # ------------------------------------------------------------------ prep
    @staticmethod
    def _prep_targets(t):
        cols = ["process_id", "case_type", "activity", "metric", "target_value", "unit",
                "comparable", "target_basis", "sop_wording", "note"]
        if t is None:
            return pd.DataFrame(columns=cols)
        t = t.copy()
        for c in cols:
            if c not in t.columns:
                t[c] = ""
        t["target_value"] = pd.to_numeric(t["target_value"], errors="coerce")
        t["comparable"] = t["comparable"].fillna("").astype(str).str.strip().str.lower()
        return t[cols]

    @staticmethod
    def _prep_sequences(s):
        cols = ["process_id", "case_type", "step_no", "activity", "team", "optional"]
        if s is None:
            return pd.DataFrame(columns=cols)
        s = s.copy()
        for c in cols:
            if c not in s.columns:
                s[c] = ""
        s["step_no"] = pd.to_numeric(s["step_no"], errors="coerce")
        s["optional"] = s["optional"].astype(str).str.strip().str.lower().eq("true")
        return s[cols]

    def _parse(self, events):
        df = events.copy()
        missing = [c for c in REQUIRED_COLS if c not in df.columns]
        if missing:
            raise ValueError(f"Event log is missing required columns: {missing}")
        for c in OPTIONAL_COLS:
            if c not in df.columns:
                df[c] = "unknown"
        q = {"rows_total": int(len(df))}
        df["status"] = df["status"].astype(str).str.strip().str.lower()
        bad_status = ~df["status"].isin(["started", "completed"])
        q["unknown_status_rows"] = int(bad_status.sum())
        df = df[~bad_status]
        s = df["timestamp"].fillna("").astype(str).str.strip()
        blank = s.eq("")
        parsed = pd.to_datetime(s.mask(blank), format="ISO8601", utc=True, errors="coerce")
        invalid = (~blank) & parsed.isna()
        q["missing_timestamp"] = int(blank.sum())
        q["invalid_timestamp"] = int(invalid.sum())
        df = df.assign(ts=parsed)[~(blank | invalid)]
        before = len(df)
        df = df.drop_duplicates(subset=["case_id", "activity", "status", "ts"])
        q["duplicate_events_removed"] = int(before - len(df))
        q["rows_used"] = int(len(df))
        for c in ["process_id", "case_type", "team", "location", "location_type"]:
            df[c] = df[c].fillna("unknown")
        return df.reset_index(drop=True), q

    # ---------------------------------------------------------------- stages
    def _build_stages(self):
        cols = ["case_id", "activity", "process_id", "case_type", "team", "location",
                "first_started", "first_completed", "completed_count", "order_ts", "prev_completed",
                "prev_team", "wait_h", "proc_h", "elapsed_h", "negative_duration", "handoff"]
        ev = self.ev
        if ev.empty:
            return pd.DataFrame(columns=cols)
        ev = ev.sort_values("ts", kind="stable")
        keys = ["case_id", "activity"]
        st = ev.groupby(keys, sort=False).agg(
            process_id=("process_id", "first"), case_type=("case_type", "first"),
            team=("team", "first"), location=("location", "first")).reset_index()
        started = ev[ev.status == "started"].groupby(keys).ts.min().rename("first_started").reset_index()
        comp = ev[ev.status == "completed"].groupby(keys).ts.agg(
            first_completed="min", completed_count="count").reset_index()
        st = st.merge(started, on=keys, how="left").merge(comp, on=keys, how="left")
        st["completed_count"] = st["completed_count"].fillna(0).astype(int)
        st["order_ts"] = st["first_started"].fillna(st["first_completed"])
        st = st.sort_values(["case_id", "order_ts"], kind="stable").reset_index(drop=True)
        st["prev_completed"] = st.groupby("case_id")["first_completed"].shift()
        st["prev_team"] = st.groupby("case_id")["team"].shift()
        hours = lambda d: d.dt.total_seconds() / 3600.0
        st["wait_h"] = hours(st["first_started"] - st["prev_completed"])
        st["proc_h"] = hours(st["first_completed"] - st["first_started"])
        st["elapsed_h"] = hours(st["first_completed"] - st["prev_completed"])
        neg = (st["wait_h"] < 0) | (st["proc_h"] < 0) | (st["elapsed_h"] < 0)
        st["negative_duration"] = neg
        st.loc[neg, ["wait_h", "proc_h", "elapsed_h"]] = np.nan   # flagged + excluded, never silently kept
        st["handoff"] = st["prev_team"].notna() & (st["team"] != st["prev_team"])
        return st[cols]

    # ----------------------------------------------------------------- cases
    def _build_cases(self):
        ev = self.ev
        cols = ["case_id", "process_id", "case_type", "location", "first_event", "last_event",
                "final_activity", "completion_known", "completed", "cycle_h", "state", "activities"]
        if ev.empty:
            return pd.DataFrame(columns=cols)
        cases = ev.groupby("case_id").agg(
            process_id=("process_id", "first"), case_type=("case_type", "first"),
            location=("location", "first"), first_event=("ts", "min"), last_event=("ts", "max"),
            activities=("activity", lambda s: set(s))).reset_index()
        if self.has_sequences:
            # a case is complete when its LAST MANDATORY step has completed (optional steps may be skipped)
            mandatory = self.seq[~self.seq.optional]
            last_act = (mandatory.sort_values("step_no").groupby(["process_id", "case_type"])
                        .activity.last().to_dict())
        else:
            last_act = {}
        cases["final_activity"] = [last_act.get((p, c)) for p, c in zip(cases.process_id, cases.case_type)]
        cases["completion_known"] = cases["final_activity"].notna()
        done = set(map(tuple, ev[ev.status == "completed"][["case_id", "activity"]].drop_duplicates().values))
        cases["completed"] = [(cid, fa) in done for cid, fa in zip(cases.case_id, cases.final_activity)]
        cases["cycle_h"] = np.where(
            cases["completed"], (cases["last_event"] - cases["first_event"]).dt.total_seconds() / 3600.0, np.nan)
        cutoff = ev["ts"].max()
        age_days = (cutoff - cases["last_event"]).dt.total_seconds() / 86400.0
        cases["state"] = np.where(
            cases["completed"], "completed",
            np.where(~cases["completion_known"], "unknown",
                     np.where(age_days <= self.stalled_after_days, "in_progress", "stalled_or_abandoned")))
        return cases[cols]

    # --------------------------------------------------------------- helpers
    def _period(self):
        if self.ev.empty:
            return "no valid events"
        return f"{self.ev.ts.min().date()} to {self.ev.ts.max().date()}"

    def _stage_target(self, pid, ct, act):
        t = self.targets
        m = t[(t.metric == "stage_elapsed_hours") & (t.process_id == pid) &
              (t.case_type == ct) & (t.activity == act)]
        if m.empty:
            return None
        r = m.iloc[0]
        if pd.isna(r.target_value) or r.comparable not in COMPARABLE_OK:
            return None
        return r

    def _step_no(self, pid, ct, act):
        m = self.seq[(self.seq.process_id == pid) & (self.seq.case_type == ct) & (self.seq.activity == act)]
        return float(m.step_no.iloc[0]) if len(m) else 999.0

    def warnings(self):
        q, w = self.quality, []
        if not self.has_targets:
            w.append("No targets file supplied: no actual-vs-target comparisons were made")
        if not self.has_sequences:
            w.append("No expected-sequences file supplied: completion, sequence and skipped-step checks are unavailable")
        if q["missing_timestamp"]:
            w.append(f"{q['missing_timestamp']} events have a missing timestamp and were excluded from calculations")
        if q["invalid_timestamp"]:
            w.append(f"{q['invalid_timestamp']} events have an unparseable timestamp and were excluded from calculations")
        if q["duplicate_events_removed"]:
            w.append(f"{q['duplicate_events_removed']} exact duplicate events were removed")
        if q["unknown_status_rows"]:
            w.append(f"{q['unknown_status_rows']} events with a status other than started/completed were excluded")
        if q.get("out_of_order_cases_excluded_from_timing"):
            w.append(f"{q['out_of_order_cases_excluded_from_timing']} cases with out-of-order activity sequences were excluded from stage timing statistics (still listed under anomalies)")
        if q["negative_duration_stages"]:
            w.append(f"{q['negative_duration_stages']} stage measurements had a negative duration and were excluded from averages")
        if len(self.cases):
            n_st = int((self.cases.state == "stalled_or_abandoned").sum())
            if n_st:
                w.append(f"{n_st} cases are incomplete with no activity for over {self.stalled_after_days} days (stalled or abandoned)")
        return w

    def envelope(self, data, warnings=None):
        """Shared response shape agreed in the team PDF: status / data / meta."""
        files = [self.source_file] + ([TARGET_FILE] if self.has_targets else []) + \
                ([SEQUENCE_FILE] if self.has_sequences else [])
        return _py({"status": "ok",
                    "data": {**data, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                    "meta": {"source_files": files,
                             "warnings": self.warnings() if warnings is None else warnings}})

    # -------------------------------------------------------------- overview
    def case_targets(self):
        out = []
        t = self.targets[self.targets.metric == "case_cycle_hours"]
        for _, r in t.iterrows():
            if pd.isna(r.target_value) or r.comparable not in COMPARABLE_OK:
                continue
            c = self.cases[(self.cases.process_id == r.process_id) & (self.cases.case_type == r.case_type) &
                           self.cases.completed & self.cases.cycle_h.notna()]
            n = len(c)
            breach = c[c.cycle_h > r.target_value]
            row = dict(process_id=r.process_id, case_type=r.case_type, target_value=r.target_value,
                       unit=r.unit, comparable=r.comparable, sop_wording=r.sop_wording,
                       n_completed=n, mean_cycle_h=_mean(c.cycle_h), median_cycle_h=_median(c.cycle_h),
                       p90_cycle_h=_p90(c.cycle_h), breach_count=len(breach),
                       breach_rate=_rate(len(breach), n), segments=[])
            opt = self.seq[(self.seq.process_id == r.process_id) & (self.seq.case_type == r.case_type) &
                           self.seq.optional]
            for act in opt.activity:
                for has in (True, False):
                    mask = pd.Series([(act in s) == has for s in c.activities], index=c.index, dtype=bool)
                    sub = c[mask]
                    nb = int((sub.cycle_h > r.target_value).sum())
                    row["segments"].append(dict(
                        optional_activity=act, activity_present=has, n_completed=len(sub),
                        mean_cycle_h=_mean(sub.cycle_h), breach_count=nb, breach_rate=_rate(nb, len(sub))))
            row["_breach_ids"] = list(breach.sort_values("cycle_h", ascending=False).case_id.head(5))
            out.append(row)
        return out

    def overview(self):
        cs = self.cases
        known = cs[cs.completion_known] if len(cs) else cs
        n_total = int(len(cs))
        n_done = int(cs.completed.sum()) if n_total else 0
        breakdown = []
        if n_total:
            for (pid, ct), g in cs.groupby(["process_id", "case_type"]):
                gk = g[g.completion_known]
                breakdown.append(dict(
                    process_id=pid, case_type=ct, total_cases=len(g), completed_cases=int(g.completed.sum()),
                    in_progress_cases=int((g.state == "in_progress").sum()),
                    stalled_or_abandoned_cases=int((g.state == "stalled_or_abandoned").sum()),
                    completion_rate=_rate(int(gk.completed.sum()), len(gk)),
                    mean_cycle_h=_mean(g.cycle_h), median_cycle_h=_median(g.cycle_h)))
        cts = self.case_targets()
        for r in cts:
            r.pop("_breach_ids", None)
        return _py(dict(
            period=self._period(),
            total_cases=n_total, completed_cases=n_done,
            completion_rate=_rate(int(known.completed.sum()) if len(known) else 0, len(known)),
            mean_cycle_h=_mean(cs.cycle_h) if n_total else None,
            median_cycle_h=_median(cs.cycle_h) if n_total else None,
            total_events_used=self.quality["rows_used"],
            process_breakdown=breakdown, case_cycle_targets=cts, data_quality=self.quality))

    # ---------------------------------------------------------------- stages
    def stages_summary(self):
        st = self.stages
        rows = []
        if st.empty:
            return rows
        for (pid, ct, act), g in st.groupby(["process_id", "case_type", "activity"]):
            e = g.elapsed_h.dropna()
            tgt = self._stage_target(pid, ct, act)
            row = dict(
                process_id=pid, case_type=ct, activity=act, step_no=self._step_no(pid, ct, act),
                team=g.team.iloc[0], n_observations=len(g), n_valid_elapsed=len(e),
                mean_wait_h=_mean(g.wait_h), median_wait_h=_median(g.wait_h),
                mean_processing_h=_mean(g.proc_h),
                mean_elapsed_h=_mean(e), median_elapsed_h=_median(e), p90_elapsed_h=_p90(e),
                handoff_observations=int(g.handoff.sum()),
                mean_handoff_wait_h=_mean(g.loc[g.handoff, "wait_h"]),
                rework_rate=_rate(int((g.completed_count > 1).sum()), len(g)),
                target_value=None, comparable=None, target_basis=None, sop_wording=None,
                target_note=None, breach_count=None, breach_rate=None)
            if tgt is not None:
                nb = int((e > tgt.target_value).sum())
                row.update(target_value=float(tgt.target_value), comparable=tgt.comparable,
                           target_basis=tgt.target_basis, sop_wording=tgt.sop_wording,
                           target_note=tgt.note, breach_count=nb, breach_rate=_rate(nb, len(e)))
            rows.append(row)
        rows.sort(key=lambda r: (r["process_id"], r["case_type"], r["step_no"]))
        return _py(rows)

    # ----------------------------------------------------------- bottlenecks
    def bottlenecks(self):
        rows = [r for r in self.stages_summary() if r["n_valid_elapsed"] >= self.min_stage_n]
        totals = {}
        for r in rows:
            k = (r["process_id"], r["case_type"])
            totals[k] = totals.get(k, 0.0) + (r["mean_elapsed_h"] or 0.0)
        for r in rows:
            tot = totals[(r["process_id"], r["case_type"])]
            r["share_of_case_time"] = _rate(r["mean_elapsed_h"] or 0.0, tot)
            if r["target_value"] is None:
                r["severity"] = "unrated"
            else:
                over = r["mean_elapsed_h"] > r["target_value"]
                br = r["breach_rate"] or 0.0
                if br >= HIGH_BREACH and over:
                    r["severity"] = "high"
                elif br >= MEDIUM_BREACH or over:
                    r["severity"] = "medium"
                else:
                    r["severity"] = "low"
        rows.sort(key=lambda r: (SEVERITY_ORDER[r["severity"]], -(r["breach_rate"] or 0.0),
                                 -(r["share_of_case_time"] or 0.0)))
        for i, r in enumerate(rows, 1):
            r["rank"] = i
        return _py(rows)

    # ------------------------------------------------------------- anomalies
    def _sequence_checks(self):
        out_of_order, skipped, unknown = [], [], []
        if not self.has_sequences or self.stages.empty:
            return out_of_order, skipped, unknown
        exp, mand = {}, {}
        for (p, c), g in self.seq.groupby(["process_id", "case_type"]):
            exp[(p, c)] = dict(zip(g.activity, g.step_no))
            mand[(p, c)] = set(g[~g.optional].activity)
        for cid, g in self.stages.groupby("case_id"):
            key = (g.process_id.iloc[0], g.case_type.iloc[0])
            e = exp.get(key)
            if not e:
                continue
            g = g.sort_values("order_ts", kind="stable")
            steps = [e[a] for a in g.activity if a in e]
            unk = [a for a in g.activity if a not in e]
            if unk:
                unknown.append((cid, unk))
            if any(b < a for a, b in zip(steps, steps[1:])):
                out_of_order.append(cid)
            if steps:
                mx, present = max(steps), set(steps)
                gap = [a for a, n in e.items() if n < mx and n not in present and a in mand[key]]
                if gap:
                    skipped.append((cid, gap))
        return out_of_order, skipped, unknown

    def anomalies(self):
        ooo, skipped, unknown = self._ooo, self._skipped, self._unknown
        st, cs = self.stages, self.cases
        rework = []
        if len(st):
            for (pid, ct, act), g in st.groupby(["process_id", "case_type", "activity"]):
                n = int((g.completed_count > 1).sum())
                if n:
                    rework.append(dict(process_id=pid, case_type=ct, activity=act, cases_with_rework=n,
                                       rework_rate=_rate(n, len(g))))
        neg_ids = list(st[st.negative_duration].case_id.unique()) if len(st) else []
        stalled = list(cs[cs.state == "stalled_or_abandoned"].case_id) if len(cs) else []
        inprog = int((cs.state == "in_progress").sum()) if len(cs) else 0
        return _py(dict(
            counts=dict(
                out_of_order_cases=len(ooo), skipped_mandatory_step_cases=len(skipped),
                unknown_activity_cases=len(unknown), cases_with_rework=int(sum(r["cases_with_rework"] for r in rework)),
                negative_duration_cases=len(neg_ids), stalled_or_abandoned_cases=len(stalled),
                in_progress_cases=inprog),
            samples=dict(
                out_of_order=ooo[:10], skipped_mandatory_step=[{"case_id": c, "missing": m} for c, m in skipped[:10]],
                negative_duration=neg_ids[:10], stalled_or_abandoned=stalled[:10]),
            rework_by_activity=sorted(rework, key=lambda r: -r["rework_rate"]),
            data_quality=self.quality))

    # -------------------------------------------------------------- findings
    def findings(self):
        period = self._period()
        src = self.source_file
        items = []
        for b in self.bottlenecks():
            if b["severity"] not in ("high", "medium"):
                continue
            st = self.stages
            bad = st[(st.process_id == b["process_id"]) & (st.case_type == b["case_type"]) &
                     (st.activity == b["activity"]) & (st.elapsed_h > b["target_value"])]
            ids = list(bad.sort_values("elapsed_h", ascending=False).case_id.head(5))
            lim = ["Observed delay does not establish the cause; treat as a hypothesis to investigate",
                   "Synthetic dataset: values illustrate the method, not real HUL performance"]
            if b["comparable"] == "approximate":
                lim.append(f"Target is approximate: {b['target_note'] or b['sop_wording']}")
            items.append((SEVERITY_ORDER[b["severity"]], -(b["breach_rate"] or 0), dict(
                domain="process",
                title=f"{b['activity']} ({b['case_type']}) often exceeds its SOP expectation",
                metric="mean_stage_elapsed_hours", actual_value=b["mean_elapsed_h"],
                target_value=b["target_value"], unit="hours", severity=b["severity"],
                scope=dict(period=period, population=f"{b['process_id']} {b['case_type']} cases with a valid measurement ({b['n_valid_elapsed']})"),
                evidence=[dict(source_file=src,
                               description=(f"Mean elapsed {b['mean_elapsed_h']:.1f}h vs target {b['target_value']:.0f}h "
                                            f"({b['sop_wording']}); {b['breach_rate']*100:.0f}% of {b['n_valid_elapsed']} cases exceeded it. "
                                            f"Mean wait {b['mean_wait_h']:.1f}h, mean processing {b['mean_processing_h']:.1f}h."),
                               record_ids=ids)],
                limitations=lim)))
        for r in self.case_targets():
            seg_max = max([s["breach_rate"] or 0 for s in r["segments"]] + [0])
            if (r["breach_rate"] or 0) < 0.10 and seg_max < 0.30:
                continue
            sev = "high" if seg_max >= 0.30 or (r["breach_rate"] or 0) >= 0.30 else "medium"
            seg_txt = "; ".join(
                f"{'with' if s['activity_present'] else 'without'} '{s['optional_activity']}': "
                f"{(s['breach_rate'] or 0)*100:.0f}% breached (n={s['n_completed']})" for s in r["segments"])
            items.append((SEVERITY_ORDER[sev], -(r["breach_rate"] or 0), dict(
                domain="process", title=f"{r['process_id']} {r['case_type']} cases sometimes exceed the end-to-end target",
                metric="mean_case_cycle_hours", actual_value=r["mean_cycle_h"], target_value=r["target_value"],
                unit="hours", severity=sev,
                scope=dict(period=period, population=f"{r['process_id']} {r['case_type']} completed cases ({r['n_completed']})"),
                evidence=[dict(source_file=src,
                               description=(f"{(r['breach_rate'] or 0)*100:.0f}% of completed cases exceeded {r['target_value']:.0f}h "
                                            f"({r['sop_wording']}). {seg_txt}"),
                               record_ids=r["_breach_ids"])],
                limitations=["Observed delay does not establish the cause; treat as a hypothesis to investigate",
                             "Synthetic dataset: values illustrate the method, not real HUL performance",
                             "Segment differences are associations, not proof that the step causes the delay"])))
        items.sort(key=lambda x: (x[0], x[1]))
        out = []
        for i, (_, _, f) in enumerate(items, 1):
            out.append({"finding_id": f"PROC-{i:03d}", **f})
        return _py(out)


if __name__ == "__main__":
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
    pa = ProcessAnalytics.from_files(folder)
    ov = pa.overview()
    print(f"Cases: {ov['total_cases']}  completed: {ov['completed_cases']}  completion rate: {ov['completion_rate']}")
    print("Warnings:")
    for w in pa.warnings():
        print("  -", w)
    print("\nTop findings:")
    for f in pa.findings()[:5]:
        print(f"  {f['finding_id']} [{f['severity']}] {f['title']}")
        print(f"      {f['evidence'][0]['description']}")
    print("\nFull envelope example (overview):")
    print(json.dumps(pa.envelope({"overview": ov}), indent=2)[:1500])
