"""Registry integrity: every KPI is documented, computable and consistent with the dataset specs."""
import json
import re
from pathlib import Path

import pandas as pd
import pytest

from kpi_engine import DATASETS, REGISTRY, REGISTRY_VERSION
from kpi_engine.registry import registry_to_dict, source_columns
from .conftest import emp, emp_syn, mkt, po

REPO_ROOT = Path(__file__).resolve().parents[3]
UNITS = {"ratio_x", "percent", "currency_per_order", "days", "points", "tasks_per_100h"}


def test_keys_are_unique_namespaced_and_legacy_ids_unique():
    assert len(REGISTRY) == len({d.key for d in REGISTRY.values()})
    for k, d in REGISTRY.items():
        assert k == d.key and re.fullmatch(r"(marketing|procurement|performance)\.[a-z0-9_]+", k), k
    legacy = [d.legacy_id for d in REGISTRY.values()]
    assert len(legacy) == len(set(legacy)) and None not in legacy


@pytest.mark.parametrize("key", list(REGISTRY))
def test_every_kpi_is_fully_documented(key):
    d = REGISTRY[key]
    for field in ("display_name", "description", "formula", "unit_label", "aggregation", "time_window", "target_note"):
        assert getattr(d, field).strip(), f"{key}.{field} empty"
    assert d.unit in UNITS and d.direction in ("higher_is_better", "lower_is_better")
    assert d.limitations, f"{key} must state its limitations"
    assert d.datasets and all(ds in DATASETS for ds in d.datasets)
    assert d.min_sample >= 1 and d.compute.scale > 0
    assert d.target_source is None  # no numeric targets exist in the supplied documents


@pytest.mark.parametrize("key", list(REGISTRY))
def test_compute_spec_columns_exist_in_every_dataset_and_rules_use_required_columns(key):
    d = REGISTRY[key]
    cs = d.compute
    frames = {"marketing_daily": mkt([dict()]), "procurement_po": po([dict()]),
              "employee_kpi_public": emp([dict()]), "employee_kpi_synthetic": emp_syn([dict()])}
    from kpi_engine.datasets import prepare
    for ds in d.datasets:
        cols = set(prepare(DATASETS[ds], frames[ds]).df.columns)
        used = {cs.numerator, cs.denominator, *cs.required, *cs.non_negative, *cs.positive,
                *(c for p in cs.at_most for c in p), *(c[0] for c in cs.in_range)}
        assert used <= cols, f"{key}/{ds}: {used - cols} not in canonical schema"
        rule_cols = {*cs.non_negative, *cs.positive, *(c for p in cs.at_most for c in p), *(c[0] for c in cs.in_range)}
        assert rule_cols <= set(cs.required), f"{key}: rule columns must be in 'required' so NaN cannot bypass a rule"
        assert {cs.numerator, cs.denominator} - {"one"} <= set(cs.required)
        assert source_columns(d, ds) or cs.denominator == "one" and cs.numerator == "one"


def test_datasets_keep_public_and_synthetic_separate():
    assert {s.data_source for s in DATASETS.values()} == {"public benchmark data", "synthetic demo data"}
    assert len({s.entity_scope for s in DATASETS.values()}) == len(DATASETS)  # no two share a population
    for s in DATASETS.values():
        assert s.data_source.startswith("synthetic") == s.entity_scope.startswith("synthetic:")
        assert s.provenance and s.declared_period


def test_committed_registry_json_is_in_sync_with_code():
    path = REPO_ROOT / "docs" / "kpi" / "kpi_registry.json"
    if not path.exists():
        pytest.skip("docs/kpi/kpi_registry.json not generated yet")
    assert json.loads(path.read_text()) == json.loads(json.dumps(registry_to_dict())), \
        "registry changed: run `python scripts/export_kpi_registry.py` and commit the output"
    assert registry_to_dict()["registry_version"] == REGISTRY_VERSION


def test_legacy_ids_exist_in_team_kpi_column_map_with_matching_label(data_dir):
    m = pd.read_csv(data_dir / "mappings" / "kpi_column_map.csv").set_index("kpi_id")
    for d in REGISTRY.values():
        assert d.legacy_id in m.index, d.legacy_id
        assert m.loc[d.legacy_id, "data_source"] == "public benchmark data"
        assert m.loc[d.legacy_id, "domain"] == {"marketing": "marketing", "procurement": "procurement",
                                                  "performance": "performance"}[d.domain]
