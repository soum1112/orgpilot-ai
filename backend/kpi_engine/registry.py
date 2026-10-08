"""Centralised KPI registry (v0.1.0).

Each KPIDefinition is both documentation and the machine-readable compute spec the engine
executes, so definitions cannot drift from code. Keys are STABLE: once published to other
members (HR KPIs, AI findings) they must not be renamed; deprecate and add instead.

Computation model (the only one in v0.1): a KPI is a RATIO OF SUMS over validated rows:

    value = scale * sum(numerator) / sum(denominator)

A plain mean is expressed as sum(x) / row-count (denominator column 'one'). Rows are validated
symmetrically for numerator and denominator; excluded rows are counted with reasons. The KPI is
not computed (value None) when the denominator is <= 0 or no valid row remains.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contract import TargetSpec
from .datasets import DATASETS, PUBLIC, SYNTHETIC

REGISTRY_VERSION = "0.1.0"


@dataclass(frozen=True)
class ComputeSpec:
    numerator: str
    denominator: str                       # 'one' => row count of valid rows
    scale: float = 1.0
    required: tuple[str, ...] = ()         # must be finite on a row or the row is excluded
    non_negative: tuple[str, ...] = ()
    positive: tuple[str, ...] = ()
    at_most: tuple[tuple[str, str], ...] = ()          # (a, b): a <= b per row
    in_range: tuple[tuple[str, float, float], ...] = ()  # (col, lo, hi) inclusive


@dataclass(frozen=True)
class KPIDefinition:
    key: str
    legacy_id: str | None                  # id in mappings/kpi_column_map.csv
    display_name: str
    domain: str                            # marketing | procurement | performance
    description: str
    formula: str                           # human readable
    compute: ComputeSpec
    unit: str                              # machine unit: ratio_x | percent | currency_per_order | days | points | tasks_per_100h
    unit_label: str                        # display; '{currency}' is substituted
    direction: str                         # higher_is_better | lower_is_better
    datasets: tuple[str, ...]
    aggregation: str
    time_window: str
    min_sample: int = 10                   # below this a value is flagged low_sample (not hidden)
    monetary: bool = False
    target_source: str | None = None
    target_note: str = "No numeric target exists in OPS-001, PRC-001 or the source notes. Targets are never invented."
    limitations: tuple[str, ...] = ()
    owner: str = "business_performance"
    status: str = "active"


_RATIO_AGG = "Ratio of sums over the selected rows. Never the average of row-level or group-level ratios."
_MEAN_AGG = "Arithmetic mean over valid records in the selected rows (sum / count). Records are not weighted."
_WINDOW_DAY = ("Rows whose date falls inside [date_from, date_to] inclusive. Default: the whole dataset period "
               "(see dataset declared_period). Trends: day / week (ISO, Mon-Sun) / month / quarter.")
_WINDOW_MONTH = ("Month-grain data: a record is included when its month lies within [month(date_from), month(date_to)] "
                 "inclusive. Default: whole dataset period. Trends: month / quarter.")

_EMP_DS = ("employee_kpi_public", "employee_kpi_synthetic")
_EMP_LIMIT = ("Public and synthetic employee results are separate series and must not be compared: different employer, "
              "period (2024 vs 2026) and the synthetic ranges were copied from the public file.",)

_DEFS: tuple[KPIDefinition, ...] = (
    # ------------------------------------------------------------------ marketing
    KPIDefinition(
        key="marketing.roas", legacy_id="M01", display_name="Return on ad spend (ROAS)", domain="marketing",
        description="Gross revenue generated per unit of advertising spend. 1.0x is break-even on gross revenue.",
        formula="sum(revenue) / sum(mark_spent)",
        compute=ComputeSpec("revenue", "spend", 1.0, required=("revenue", "spend"), non_negative=("revenue", "spend")),
        unit="ratio_x", unit_label="x (revenue per 1 unit of spend)", direction="higher_is_better",
        datasets=("marketing_daily",), aggregation=_RATIO_AGG, time_window=_WINDOW_DAY, monetary=True,
        limitations=("Revenue is gross, not margin: ROAS 1.0 is not profit break-even.",
                     "Single month (2021-02) of public data: no seasonality, not current.",
                     "Ranking is sensitive to outlier days (e.g. youtube_blogger spend 880k on one day).",
                     "Spend-weighted: a simple mean of campaign ROAS (1.370) differs from total ROAS (1.402)."),
    ),
    KPIDefinition(
        key="marketing.ctr_pct", legacy_id="M02", display_name="Click-through rate (CTR)", domain="marketing",
        description="Share of impressions that resulted in a click.",
        formula="sum(clicks) / sum(impressions) * 100",
        compute=ComputeSpec("clicks", "impressions", 100.0, required=("clicks", "impressions"),
                            non_negative=("clicks", "impressions"), at_most=(("clicks", "impressions"),)),
        unit="percent", unit_label="% of impressions", direction="higher_is_better",
        datasets=("marketing_daily",), aggregation=_RATIO_AGG, time_window=_WINDOW_DAY,
        limitations=("Do NOT compare CTR or impression volume across channel types: media (~0.04%) vs influencer (~1%) "
                     "measure different things.",
                     "Single month (2021-02) of public data."),
    ),
    KPIDefinition(
        key="marketing.cost_per_order", legacy_id="M03", display_name="Cost per order (CPO)", domain="marketing",
        description="Advertising spend per order, including spend on days with zero orders.",
        formula="sum(mark_spent) / sum(orders)",
        compute=ComputeSpec("spend", "orders", 1.0, required=("spend", "orders"), non_negative=("spend", "orders")),
        unit="currency_per_order", unit_label="{currency} per order", direction="lower_is_better",
        datasets=("marketing_daily",), aggregation=_RATIO_AGG, time_window=_WINDOW_DAY, monetary=True,
        limitations=("Currency is not stated in the source.",
                     "Undefined (value None) when total orders in the selection is 0; never reported as 0 or infinity.",
                     "19 campaign-days have zero orders; their spend stays in the numerator (it is real cost).",
                     "Single month (2021-02) of public data."),
    ),
    # ------------------------------------------------------------------ procurement
    KPIDefinition(
        key="procurement.savings_pct", legacy_id="R01", display_name="Procurement savings", domain="procurement",
        description="Negotiated discount versus list price, weighted by PO value.",
        formula="sum(Quantity * (Unit_Price - Negotiated_Price)) / sum(Quantity * Unit_Price) * 100",
        compute=ComputeSpec("savings_value", "po_value_list", 100.0,
                            required=("quantity", "unit_price", "negotiated_price", "savings_value", "po_value_list"),
                            non_negative=("quantity", "unit_price", "negotiated_price")),
        unit="percent", unit_label="% of list value", direction="higher_is_better",
        datasets=("procurement_po",), aggregation=_RATIO_AGG, time_window=_WINDOW_DAY, monetary=True,
        limitations=("Unit_Price is treated as the list/baseline price; the source does not define it.",
                     "Cancelled and Pending POs are included by default (this reproduces the published supplier/quarter files); "
                     "filter status to restrict to realised orders. Savings on cancelled POs are not realised.",
                     "Nearly flat across suppliers (7.8% to 8.3%): fine as a headline, weak for ranking.",
                     "Prices are similar across categories, so spend mixes unit types.",
                     "Currency is not stated in the source."),
    ),
    KPIDefinition(
        key="procurement.avg_lead_time_days", legacy_id="R02", display_name="Average lead time", domain="procurement",
        description="Mean days between order date and delivery date over POs with a valid delivery date.",
        formula="mean(Delivery_Date - Order_Date) over rows with both dates and Delivery_Date >= Order_Date",
        compute=ComputeSpec("lead_time_days", "one", 1.0, required=("lead_time_days",), non_negative=("lead_time_days",)),
        unit="days", unit_label="days", direction="lower_is_better",
        datasets=("procurement_po",), aggregation=_MEAN_AGG, time_window=_WINDOW_DAY,
        limitations=("87 POs have no delivery date (68 of them marked Delivered): likely a data gap, excluded not imputed.",
                     "1 PO (PO-00101) has delivery before order (-5 days): excluded.",
                     "Cancelled/Pending POs also carry delivery dates; the default keeps them (reproduces the published files). "
                     "A warning states how many are included; filter status=Delivered for a stricter view.",
                     "Orders are placed by Order_Date: the last quarter (2024Q1) holds only 2 POs."),
    ),
    KPIDefinition(
        key="procurement.defect_rate_pct", legacy_id="R03", display_name="Defect rate (units-weighted)", domain="procurement",
        description="Defective units as a share of units, over POs that report a defect count.",
        formula="sum(Defective_Units) / sum(Quantity) * 100, over rows where Defective_Units is recorded",
        compute=ComputeSpec("defective_units", "quantity", 100.0, required=("defective_units", "quantity"),
                            non_negative=("defective_units", "quantity"), at_most=(("defective_units", "quantity"),)),
        unit="percent", unit_label="% of units", direction="lower_is_better",
        datasets=("procurement_po",), aggregation=_RATIO_AGG, time_window=_WINDOW_DAY,
        limitations=("136 POs (17.5%) have no Defective_Units; they are excluded from numerator AND denominator. "
                     "Using all quantity as denominator would understate the rate (5.64% vs 6.80%).",
                     "Missingness is not random across statuses (102 of 136 are Delivered).",
                     "Resolves the open R03 formula question in kpi_column_map.csv: this definition reproduces the published "
                     "supplier and quarter summary files exactly."),
    ),
    KPIDefinition(
        key="procurement.compliance_rate_pct", legacy_id="R04", display_name="Compliance rate", domain="procurement",
        description="Share of POs flagged compliant.",
        formula="count(Compliance = 'Yes') / count(POs with a Yes/No Compliance value) * 100",
        compute=ComputeSpec("is_compliant", "one", 100.0, required=("is_compliant",)),
        unit="percent", unit_label="% of POs", direction="higher_is_better",
        datasets=("procurement_po",), aggregation="Share of POs (count-based, not value-weighted).", time_window=_WINDOW_DAY,
        limitations=("'Compliance' is not defined anywhere in the source: treat as an undocumented binary flag.",
                     "Large supplier spread (61% to 98%) makes it informative, but the meaning of 'compliant' is unknown."),
    ),
    # ------------------------------------------------------------------ performance
    KPIDefinition(
        key="performance.avg_performance_score", legacy_id="E01", display_name="Average performance score",
        domain="performance",
        description="Mean monthly performance score across employee-month records.",
        formula="mean(performance_score)",
        compute=ComputeSpec("performance_score", "one", 1.0, required=("performance_score",), non_negative=("performance_score",)),
        unit="points", unit_label="points (scale undocumented)", direction="higher_is_better",
        datasets=_EMP_DS, aggregation=_MEAN_AGG, time_window=_WINDOW_MONTH,
        limitations=("The score scale is undocumented (observed 0 to 30.89 public, 0 to 29.5 synthetic).",
                     "Weakly related to every other recorded driver (linear R^2 ~ 0.03 in the public file): descriptive only, "
                     "no causal claims.",
                     "Public file: 200 employee-month keys appear twice with different attributes; department is unstable per "
                     "employee, and 2024-02 is absent. Differences between departments are small (13.3 to 14.2).") + _EMP_LIMIT,
    ),
    KPIDefinition(
        key="performance.avg_attendance_rate_pct", legacy_id="E02", display_name="Average attendance rate",
        domain="performance",
        description="Mean monthly attendance rate across employee-month records.",
        formula="mean(attendance_rate), attendance_rate already a percentage 0 to 100",
        compute=ComputeSpec("attendance_rate", "one", 1.0, required=("attendance_rate",), in_range=(("attendance_rate", 0.0, 100.0),)),
        unit="percent", unit_label="%", direction="higher_is_better",
        datasets=_EMP_DS, aggregation=_MEAN_AGG + " Not hours-weighted (scheduled hours are not recorded).",
        time_window=_WINDOW_MONTH,
        limitations=("Values outside 0 to 100 are excluded; a column whose values all lie within 0 to 1 is rejected as a "
                     "probable fraction (status invalid_units) rather than silently rescaled.",) + _EMP_LIMIT,
    ),
    KPIDefinition(
        key="performance.tasks_per_100h", legacy_id="E03", display_name="Tasks per 100 hours", domain="performance",
        description="Tasks completed per 100 hours worked.",
        formula="sum(tasks_completed) / sum(monthly_hours_worked) * 100",
        compute=ComputeSpec("tasks_completed", "monthly_hours_worked", 100.0,
                            required=("tasks_completed", "monthly_hours_worked"),
                            non_negative=("tasks_completed",), positive=("monthly_hours_worked",)),
        unit="tasks_per_100h", unit_label="tasks per 100 hours", direction="higher_is_better",
        datasets=_EMP_DS, aggregation=_RATIO_AGG + " (differs slightly from averaging the per-row Task_per_100h column)",
        time_window=_WINDOW_MONTH,
        limitations=("Records with hours <= 0 are excluded.",
                     "Tasks are not weighted by size or difficulty.") + _EMP_LIMIT,
    ),
)

REGISTRY: dict[str, KPIDefinition] = {d.key: d for d in _DEFS}

# Targets are registered ONLY when a source document states them. None exist for the KPIs above.
# (OPS-001 states 3-day closure and 85% completion, but those are PROCESS KPIs owned elsewhere.)
TARGETS: dict[str, TargetSpec] = {}


def kpis_for_dataset(dataset_id: str) -> list[KPIDefinition]:
    return [d for d in REGISTRY.values() if dataset_id in d.datasets]


def source_columns(defn: KPIDefinition, dataset_id: str) -> list[str]:
    """Raw source columns (as named in the CSV) behind a KPI for one dataset."""
    spec = DATASETS[dataset_id]
    cs = defn.compute
    used = [cs.numerator, cs.denominator, *cs.required]
    seen: list[str] = []
    for canon in used:
        if canon == "one":
            continue
        for raw in spec.raw_columns_for(canon):
            if raw not in seen:
                seen.append(raw)
    return seen


def registry_to_dict() -> dict[str, Any]:
    kpis = []
    for d in REGISTRY.values():
        cs = d.compute
        kpis.append({
            "key": d.key, "legacy_id": d.legacy_id, "display_name": d.display_name, "domain": d.domain,
            "description": d.description, "formula": d.formula, "unit": d.unit, "unit_label": d.unit_label,
            "direction": d.direction, "datasets": list(d.datasets),
            "source_columns": {ds: source_columns(d, ds) for ds in d.datasets},
            "compute": {"numerator": cs.numerator, "denominator": cs.denominator, "scale": cs.scale,
                        "required": list(cs.required), "non_negative": list(cs.non_negative),
                        "positive": list(cs.positive), "at_most": [list(p) for p in cs.at_most],
                        "in_range": [list(p) for p in cs.in_range]},
            "aggregation": d.aggregation, "time_window": d.time_window, "min_sample": d.min_sample,
            "monetary": d.monetary,
            "target": ({"value": TARGETS[d.key].value, "source": TARGETS[d.key].source} if d.key in TARGETS
                       else {"value": None, "source": d.target_source, "note": d.target_note}),
            "limitations": list(d.limitations), "owner": d.owner, "status": d.status,
        })
    datasets = []
    for s in DATASETS.values():
        datasets.append({
            "dataset_id": s.dataset_id, "display_name": s.display_name, "data_source": s.data_source,
            "entity_scope": s.entity_scope, "file": s.relative_path, "grain": s.grain,
            "key_columns": list(s.key_columns), "key_semantics": s.key_semantics, "date_grain": s.date_grain,
            "declared_period": s.declared_period, "currency": s.currency or "not stated in source",
            "group_columns": list(s.group_columns), "provenance": dict(s.provenance),
            "derived_from_ranges_of": s.derived_from_ranges_of, "notes": list(s.notes),
        })
    return {"registry_version": REGISTRY_VERSION, "datasets": datasets, "kpis": kpis}
