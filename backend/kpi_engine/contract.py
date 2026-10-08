"""Result objects returned by the KPI engine.

PROPOSED shared contract (v0.1) - to be confirmed with the AI-findings owner (Member 4).
Design rules:
  * every number says what it is: ``evidence_type`` is observed | target | estimate | hypothesis.
    The engine itself only ever emits ``observed`` values and ``target`` blocks; estimates and
    hypotheses are produced downstream and must carry their own evidence_type.
  * a value is ``None`` (never 0, inf or NaN) whenever ``status != "ok"``.
  * every result names its dataset and data_source so public and synthetic data never blur.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

CONTRACT_VERSION = "0.1-proposed"


class EvidenceType(str, Enum):
    OBSERVED = "observed"
    TARGET = "target"
    ESTIMATE = "estimate"
    HYPOTHESIS = "hypothesis"


class Status(str, Enum):
    OK = "ok"
    NO_DATA = "no_data"                          # no rows after filters
    INVALID_DENOMINATOR = "invalid_denominator"  # denominator <= 0 / no valid rows
    INVALID_UNITS = "invalid_units"              # unit/scale/currency inconsistency detected


@dataclass(frozen=True)
class TargetSpec:
    """A target is only valid together with the document/source it came from."""
    value: float
    source: str
    direction: str | None = None  # override registry direction if the source says otherwise

    def __post_init__(self) -> None:
        if not isinstance(self.value, (int, float)) or isinstance(self.value, bool) or not math.isfinite(self.value):
            raise ValueError("target value must be a finite number")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("a target requires a non-empty 'source' (document or owner); targets are never invented")
        if self.direction not in (None, "higher_is_better", "lower_is_better"):
            raise ValueError("target direction must be higher_is_better or lower_is_better")


def _r(x: Any) -> Any:
    """Round floats for stable JSON; leave everything else alone."""
    if isinstance(x, float):
        return round(x, 6) if math.isfinite(x) else None
    if isinstance(x, dict):
        return {k: _r(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_r(v) for v in x]
    if isinstance(x, Enum):
        return x.value
    return x


@dataclass
class KPIResult:
    key: str
    display_name: str
    unit: str
    unit_label: str
    value: float | None
    status: Status
    dataset_id: str
    data_source: str
    period: dict[str, Any]
    filters: dict[str, Any]
    group: dict[str, Any] | None
    n_rows_input: int
    n_rows_used: int
    n_rows_excluded: int
    exclusion_reasons: dict[str, int]
    numerator_total: float | None
    denominator_total: float | None
    warnings: list[str] = field(default_factory=list)
    target: dict[str, Any] = field(default_factory=dict)
    evidence_type: EvidenceType = EvidenceType.OBSERVED
    registry_version: str = ""
    contract_version: str = CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return _r({
            "key": self.key, "display_name": self.display_name, "evidence_type": self.evidence_type,
            "value": self.value, "unit": self.unit, "unit_label": self.unit_label, "status": self.status,
            "dataset_id": self.dataset_id, "data_source": self.data_source, "period": self.period,
            "filters": self.filters, "group": self.group,
            "n_rows_input": self.n_rows_input, "n_rows_used": self.n_rows_used,
            "n_rows_excluded": self.n_rows_excluded, "exclusion_reasons": self.exclusion_reasons,
            "numerator_total": self.numerator_total, "denominator_total": self.denominator_total,
            "warnings": self.warnings, "target": self.target,
            "registry_version": self.registry_version, "contract_version": self.contract_version,
        })


@dataclass
class TrendPoint:
    period: str
    period_start: str
    period_end: str
    value: float | None
    status: Status
    n_rows_used: int
    low_sample: bool
    partial_period: bool
    change_abs: float | None
    change_pct: float | None
    change_note: str | None

    def to_dict(self) -> dict[str, Any]:
        return _r(self.__dict__.copy())


@dataclass
class TrendResult:
    key: str
    display_name: str
    unit: str
    unit_label: str
    dataset_id: str
    data_source: str
    freq: str
    min_sample: int
    filters: dict[str, Any]
    points: list[TrendPoint]
    gap_periods: list[str]
    warnings: list[str]
    evidence_type: EvidenceType = EvidenceType.OBSERVED
    registry_version: str = ""
    contract_version: str = CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return _r({
            "key": self.key, "display_name": self.display_name, "evidence_type": self.evidence_type,
            "unit": self.unit, "unit_label": self.unit_label, "dataset_id": self.dataset_id,
            "data_source": self.data_source, "freq": self.freq, "min_sample": self.min_sample,
            "filters": self.filters, "points": [p.to_dict() for p in self.points],
            "gap_periods": self.gap_periods, "warnings": self.warnings,
            "registry_version": self.registry_version, "contract_version": self.contract_version,
        })
