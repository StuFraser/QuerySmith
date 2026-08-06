"""Request/response models for the local web UI's JSON API (see
design-notes/execution-plan-web-ui.md). This is the one place in the
codebase that uses pydantic rather than plain dataclasses -- deliberate,
since FastAPI's request validation and OpenAPI docs are built around it;
everything downstream of the API boundary still uses the existing
dataclass-based IR/Finding/Narration types unchanged.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from querysmith.db.connection import DEFAULT_ODBC_DRIVER
from querysmith.narration import DEFAULT_MODEL

__all__ = [
    "ConnectionRequest",
    "ConnectionStatusResponse",
    "ViewItem",
    "ViewsResponse",
    "QueryRequest",
    "FindingItem",
    "PlanSummaryItem",
    "NarrationItem",
    "QueryResponse",
    "ProposeFixRequest",
    "FixItem",
    "ProposeFixResponse",
]


class ConnectionRequest(BaseModel):
    server: str
    database: str
    user: str
    password: str
    driver: str = DEFAULT_ODBC_DRIVER
    trust_server_certificate: bool = True
    timeout_s: float = 60.0


class ConnectionStatusResponse(BaseModel):
    connected: bool
    server: Optional[str] = None
    database: Optional[str] = None
    user: Optional[str] = None
    driver: Optional[str] = None
    trust_server_certificate: Optional[bool] = None
    # password intentionally has no field here -- never echoed back


class ViewItem(BaseModel):
    schema_name: str
    view_name: str
    qualified_name: str
    select_body: Optional[str] = None


class ViewsResponse(BaseModel):
    views: list[ViewItem]


class QueryRequest(BaseModel):
    query: str
    narrate: bool = True
    # See design-notes/execution-plan-web-ui.md: parse_plan_xml's redact
    # param is currently an identity-passthrough stub (real literal
    # redaction is deferred). Wired through end-to-end anyway so only the
    # UI copy needs to change once real redaction lands.
    redact: bool = False
    model: str = DEFAULT_MODEL
    ollama_timeout_s: float = 600.0


class FindingItem(BaseModel):
    rule_id: str
    severity: str
    operator_id: Optional[str] = None
    summary: str
    detail: str
    suggested_fix: Optional[str] = None
    explanation: Optional[str] = None
    explanation_source: Optional[str] = None
    model_suggested_fix: Optional[str] = None


class PlanSummaryItem(BaseModel):
    engine: str
    engine_version: Optional[str] = None
    database_name: Optional[str] = None
    object_type: str
    statement_type: str
    statement_text: str
    total_estimated_cost: Optional[float] = None
    total_actual_duration_ms: Optional[float] = None
    total_actual_rows: Optional[int] = None
    operator_count: int


class NarrationItem(BaseModel):
    overview: str
    overview_source: str
    degraded: bool
    degraded_reason: Optional[str] = None
    model_name: str


class QueryResponse(BaseModel):
    summary: PlanSummaryItem
    findings: list[FindingItem]
    narration: Optional[NarrationItem] = None


class ProposeFixRequest(BaseModel):
    model: str = DEFAULT_MODEL
    ollama_timeout_s: float = 600.0


class FixItem(BaseModel):
    finding_index: int
    rewritten_query: Optional[str] = None
    index_script: Optional[str] = None


class ProposeFixResponse(BaseModel):
    fixes: list[FixItem]
    degraded: bool
    degraded_reason: Optional[str] = None
    model_name: str
