"""Dialect-agnostic execution plan IR (see design-notes/execution-plan-ir-schema.md)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Engine(str, Enum):
    SQLSERVER = "sqlserver"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"


class PlanSource(str, Enum):
    ESTIMATED = "estimated"
    ACTUAL = "actual"


class ObjectType(str, Enum):
    ADHOC_QUERY = "adhoc_query"
    STORED_PROCEDURE = "stored_procedure"
    FUNCTION = "function"
    TRIGGER = "trigger"
    VIEW = "view"


class StatementType(str, Enum):
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    MERGE = "MERGE"
    OTHER = "OTHER"


class OperatorType(str, Enum):
    TABLE_SCAN = "table_scan"
    INDEX_SEEK = "index_seek"
    INDEX_SCAN = "index_scan"
    BOOKMARK_LOOKUP = "bookmark_lookup"
    JOIN_NESTED_LOOP = "join_nested_loop"
    JOIN_HASH = "join_hash"
    JOIN_MERGE = "join_merge"
    SORT = "sort"
    AGGREGATE = "aggregate"
    # Additive beyond the IR doc's 9-entry vocabulary table: SQL Server plans
    # routinely contain operators the doc doesn't name (Compute Scalar, Filter,
    # Top, Parallelism operators, Spool variants, ...). Falling back here keeps
    # the adapter from crashing or fabricating a normalized type it can't justify.
    OTHER = "other"


class JoinType(str, Enum):
    NESTED_LOOP = "nested_loop"
    HASH = "hash"
    MERGE = "merge"


class AccessType(str, Enum):
    SEEK = "seek"
    SCAN = "scan"
    BOOKMARK_LOOKUP = "bookmark_lookup"
    FULL_SCAN = "full_scan"


class WarningType(str, Enum):
    IMPLICIT_CONVERSION = "implicit_conversion"
    TEMPDB_SPILL = "tempdb_spill"
    NO_JOIN_PREDICATE = "no_join_predicate"
    COLUMN_WITH_NO_STATS = "column_with_no_stats"
    MEMORY_GRANT_EXCESSIVE = "memory_grant_excessive"
    CARDINALITY_SKEW = "cardinality_skew"
    OTHER = "other"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class ObjectRef:
    schema: Optional[str] = None
    table: Optional[str] = None
    index: Optional[str] = None


@dataclass
class PlanMeta:
    engine: Engine
    engine_version: Optional[str]
    plan_source: PlanSource
    captured_at: Optional[datetime]
    object_type: ObjectType
    object_name: Optional[str]
    database_name: Optional[str]


@dataclass
class Statement:
    text: str
    statement_type: StatementType
    total_estimated_cost: Optional[float] = None
    total_actual_duration_ms: Optional[float] = None
    total_actual_rows: Optional[int] = None


@dataclass
class Operator:
    id: str
    operator_type: OperatorType
    physical_op_raw: str
    object_ref: Optional[ObjectRef] = None
    estimated_rows: Optional[float] = None
    actual_rows: Optional[float] = None
    row_estimate_ratio: Optional[float] = None
    estimated_cost: Optional[float] = None
    estimated_cost_pct_of_total: Optional[float] = None
    actual_duration_ms: Optional[float] = None
    predicates: list[str] = field(default_factory=list)
    join_type: Optional[JoinType] = None
    access_type: Optional[AccessType] = None
    sort_present: bool = False
    parallel: bool = False
    memory_grant_kb: Optional[int] = None
    tempdb_spill: bool = False
    children: list["Operator"] = field(default_factory=list)


@dataclass
class Warning:
    type: WarningType
    detail: str
    operator_id: Optional[str] = None
    # Doc's table lists this as a required enum, but its own prose assigns
    # severity-setting to the Tier 0 rules engine, not the adapter -- which
    # doesn't exist yet. Optional here so the adapter never fabricates a
    # judgment call it has no basis for.
    severity: Optional[Severity] = None


@dataclass
class MissingIndex:
    table: str
    columns_equality: list[str] = field(default_factory=list)
    columns_inequality: list[str] = field(default_factory=list)
    columns_include: list[str] = field(default_factory=list)
    estimated_impact: Optional[float] = None


@dataclass
class IRPlan:
    meta: PlanMeta
    statement: Statement
    root_operator: Operator
    warnings: list[Warning] = field(default_factory=list)
    missing_indexes: list[MissingIndex] = field(default_factory=list)
