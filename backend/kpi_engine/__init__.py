"""OrgPilot AI shared KPI engine (pure Python + pandas, no Django imports).

Public surface:
    KPIEngine      - compute KPIs / trends / target comparisons
    REGISTRY       - stable KPI definitions (single source of truth)
    DATASETS       - dataset specs (provenance, grain, period, canonical schema)
"""
from .contract import (  # noqa: F401
    CONTRACT_VERSION, EvidenceType, KPIResult, Status, TargetSpec, TrendPoint, TrendResult,
)
from .datasets import DATASETS, PUBLIC, SYNTHETIC, SchemaError  # noqa: F401
from .engine import KPIEngine, KPIEngineError  # noqa: F401
from .registry import REGISTRY, REGISTRY_VERSION, TARGETS  # noqa: F401
