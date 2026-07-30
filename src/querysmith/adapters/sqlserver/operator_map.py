"""SQL Server PhysicalOp/LogicalOp -> normalized IR vocabulary lookup tables."""

from querysmith.ir.models import OperatorType, WarningType

# "Hash Match" is deliberately absent here: SQL Server reuses that PhysicalOp for
# both hash joins and hash aggregates/distinct, so it can only be resolved via
# LogicalOp (see HASH_MATCH_LOGICAL_OP_MAP below).
PHYSICAL_OP_MAP: dict[str, OperatorType] = {
    "Table Scan": OperatorType.TABLE_SCAN,
    "Index Seek": OperatorType.INDEX_SEEK,
    "Clustered Index Seek": OperatorType.INDEX_SEEK,
    "Index Scan": OperatorType.INDEX_SCAN,
    "Clustered Index Scan": OperatorType.INDEX_SCAN,
    "Nested Loops": OperatorType.JOIN_NESTED_LOOP,
    "Merge Join": OperatorType.JOIN_MERGE,
    "Sort": OperatorType.SORT,
    "Stream Aggregate": OperatorType.AGGREGATE,
}

# Physical ops that can represent a bookmark lookup when Lookup="1" is present
# on their detail element, instead of their PHYSICAL_OP_MAP meaning.
LOOKUP_CAPABLE_PHYSICAL_OPS = {"Clustered Index Seek", "Index Seek", "RID Lookup"}

HASH_MATCH_LOGICAL_OP_MAP: dict[str, OperatorType] = {
    "Inner Join": OperatorType.JOIN_HASH,
    "Left Outer Join": OperatorType.JOIN_HASH,
    "Right Outer Join": OperatorType.JOIN_HASH,
    "Full Outer Join": OperatorType.JOIN_HASH,
    "Left Semi Join": OperatorType.JOIN_HASH,
    "Left Anti Semi Join": OperatorType.JOIN_HASH,
    "Aggregate": OperatorType.AGGREGATE,
    "Partial Aggregate": OperatorType.AGGREGATE,
    "Distinct": OperatorType.AGGREGATE,
}

HASH_JOIN_LOGICAL_OPS = {
    "Inner Join",
    "Left Outer Join",
    "Right Outer Join",
    "Full Outer Join",
    "Left Semi Join",
    "Left Anti Semi Join",
}

WARNING_TAG_MAP: dict[str, WarningType] = {
    "SpillToTempDb": WarningType.TEMPDB_SPILL,
    "NoJoinPredicate": WarningType.NO_JOIN_PREDICATE,
    "ColumnsWithNoStatistics": WarningType.COLUMN_WITH_NO_STATS,
    "PlanAffectingConvert": WarningType.IMPLICIT_CONVERSION,
    "MemoryGrantWarning": WarningType.MEMORY_GRANT_EXCESSIVE,
}
