"""Tier 1 narration data structures (see design-notes/execution-plan-agent-scope.md)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from querysmith.ir.models import Severity


@dataclass
class OperatorHighlight:
    id: str
    operator_type: str
    physical_op_raw: str
    object_ref: Optional[str] = None
    access_type: Optional[str] = None
    estimated_rows: Optional[float] = None
    actual_rows: Optional[float] = None
    row_estimate_ratio: Optional[float] = None
    estimated_cost_pct_of_total: Optional[float] = None
    actual_duration_ms: Optional[float] = None
    tempdb_spill: bool = False
    parallel: bool = False


@dataclass
class PlanSummary:
    engine: str
    engine_version: Optional[str]
    database_name: Optional[str]
    object_type: str
    object_name: Optional[str]
    plan_source: str
    statement_type: str
    statement_text: str
    total_estimated_cost: Optional[float]
    total_actual_duration_ms: Optional[float]
    total_actual_rows: Optional[int]
    operator_count: int
    notable_operators: list[OperatorHighlight] = field(default_factory=list)


@dataclass
class FindingNarration:
    rule_id: str
    severity: Severity
    operator_id: Optional[str]
    summary: str
    detail: str
    explanation: str
    explanation_source: str


@dataclass
class Narration:
    overview: str
    overview_source: str
    findings: list[FindingNarration] = field(default_factory=list)
    degraded: bool = False
    degraded_reason: Optional[str] = None
    model_name: str = ""
