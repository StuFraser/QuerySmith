"""FastAPI app for the QuerySmith local web UI (see
design-notes/execution-plan-web-ui.md). Thin HTTP layer over the existing
capture -> IR -> rules -> narration pipeline (mirrors cli.py's `run`/
`format_report` orchestration) -- route handlers only translate exceptions
into HTTP responses and shape pydantic models; no business logic lives
here. DI hooks (get_connect_fn/get_capture_fn/get_list_views_fn) follow the
same injectable-callable pattern as capture_fn/connect_fn/client elsewhere
in this codebase, overridable in tests via app.dependency_overrides.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import pyodbc
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from querysmith.adapters.sqlserver import parse_plan_xml
from querysmith.db import DBCaptureError, QueryValidationError, capture_plan_xml, list_views
from querysmith.db.connection import connect
from querysmith.ir.models import ObjectType, PlanSource
from querysmith.narration import (
    DEFAULT_MODEL,
    FixProposal,
    Narration,
    PlanSummary,
    get_narration,
    propose_fixes,
    summarize_plan,
)
from querysmith.narration.ollama_client import generate_json
from querysmith.rules import Finding, evaluate
from querysmith.web.last_result import LastResult, LastResultStore, NoResultAvailableError, get_last_result_store
from querysmith.web.schemas import (
    ConnectionRequest,
    ConnectionStatusResponse,
    FindingItem,
    FixItem,
    NarrationItem,
    PlanSummaryItem,
    ProposeFixRequest,
    ProposeFixResponse,
    QueryRequest,
    QueryResponse,
    ViewItem,
    ViewsResponse,
)
from querysmith.web.session import ConnectionParams, NotConnectedError, SessionStore, get_session_store

__all__ = ["create_app"]

STATIC_DIR = Path(__file__).parent / "static"

ConnectFn = Callable[..., pyodbc.Connection]
CaptureFn = Callable[..., str]
ListViewsFn = Callable[..., list]
GenerateFn = Callable[[str, str], dict]

logger = logging.getLogger(__name__)


def get_connect_fn() -> ConnectFn:
    return connect


def get_capture_fn() -> CaptureFn:
    return capture_plan_xml


def get_list_views_fn() -> ListViewsFn:
    return list_views


def get_generate_fn() -> Callable[..., dict]:
    return generate_json


def _conn_kwargs(params: ConnectionParams) -> dict:
    return dict(
        server=params.server,
        database=params.database,
        user=params.user,
        password=params.password,
        driver=params.driver,
        trust_server_certificate=params.trust_server_certificate,
        timeout_s=params.timeout_s,
    )


def _require_connection(store: SessionStore) -> ConnectionParams:
    try:
        return store.get()
    except NotConnectedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _require_last_result(store: LastResultStore) -> LastResult:
    try:
        return store.get()
    except NoResultAvailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _make_ollama_client(generate_fn: Callable[..., dict], timeout_s: float) -> GenerateFn:
    def client(prompt: str, model: str) -> dict:
        return generate_fn(prompt, model, timeout_s=timeout_s)

    return client


def _to_query_response(
    summary: PlanSummary, findings: list[Finding], narration: Optional[Narration]
) -> QueryResponse:
    narration_by_index = {i: fn for i, fn in enumerate(narration.findings)} if narration else {}
    finding_items = []
    for i, finding in enumerate(findings):
        fn = narration_by_index.get(i)
        finding_items.append(
            FindingItem(
                rule_id=finding.rule_id,
                severity=finding.severity.value,
                operator_id=finding.operator_id,
                summary=finding.summary,
                detail=finding.detail,
                suggested_fix=finding.suggested_fix,
                explanation=fn.explanation if fn else None,
                explanation_source=fn.explanation_source if fn else None,
                model_suggested_fix=fn.suggested_fix if fn else None,
            )
        )
    summary_item = PlanSummaryItem(
        engine=summary.engine,
        engine_version=summary.engine_version,
        database_name=summary.database_name,
        object_type=summary.object_type,
        statement_type=summary.statement_type,
        statement_text=summary.statement_text,
        total_estimated_cost=summary.total_estimated_cost,
        total_actual_duration_ms=summary.total_actual_duration_ms,
        total_actual_rows=summary.total_actual_rows,
        operator_count=summary.operator_count,
    )
    narration_item = (
        NarrationItem(
            overview=narration.overview,
            overview_source=narration.overview_source,
            degraded=narration.degraded,
            degraded_reason=narration.degraded_reason,
            model_name=narration.model_name,
        )
        if narration is not None
        else None
    )
    return QueryResponse(summary=summary_item, findings=finding_items, narration=narration_item)


def _to_propose_fix_response(proposal: FixProposal) -> ProposeFixResponse:
    return ProposeFixResponse(
        fixes=[
            FixItem(finding_index=f.finding_index, rewritten_query=f.rewritten_query, index_script=f.index_script)
            for f in proposal.fixes
        ],
        degraded=proposal.degraded,
        degraded_reason=proposal.degraded_reason,
        model_name=proposal.model_name,
    )


def create_app() -> FastAPI:
    app = FastAPI(title="QuerySmith", docs_url="/api/docs", openapi_url="/api/openapi.json")

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Never leak exception text/stack trace to the client -- log
        # server-side only, and never let params.password/body.password
        # reach this log call.
        logger.exception("Unhandled error in %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    @app.post("/api/connection", response_model=ConnectionStatusResponse)
    def create_connection(
        body: ConnectionRequest,
        store: SessionStore = Depends(get_session_store),
        connect_fn: ConnectFn = Depends(get_connect_fn),
    ) -> ConnectionStatusResponse:
        try:
            connection = connect_fn(
                server=body.server,
                database=body.database,
                user=body.user,
                password=body.password,
                driver=body.driver,
                trust_server_certificate=body.trust_server_certificate,
                timeout_s=body.timeout_s,
            )
            connection.close()
        except DBCaptureError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        store.set(
            ConnectionParams(
                server=body.server,
                database=body.database,
                user=body.user,
                password=body.password,
                driver=body.driver,
                trust_server_certificate=body.trust_server_certificate,
                timeout_s=body.timeout_s,
            )
        )
        return ConnectionStatusResponse(
            connected=True,
            server=body.server,
            database=body.database,
            user=body.user,
            driver=body.driver,
            trust_server_certificate=body.trust_server_certificate,
        )

    @app.get("/api/connection", response_model=ConnectionStatusResponse)
    def get_connection(store: SessionStore = Depends(get_session_store)) -> ConnectionStatusResponse:
        if not store.is_connected():
            return ConnectionStatusResponse(connected=False)
        params = store.get()
        return ConnectionStatusResponse(
            connected=True,
            server=params.server,
            database=params.database,
            user=params.user,
            driver=params.driver,
            trust_server_certificate=params.trust_server_certificate,
        )

    @app.delete("/api/connection", status_code=204)
    def delete_connection(
        store: SessionStore = Depends(get_session_store),
        last_result_store: LastResultStore = Depends(get_last_result_store),
    ) -> None:
        store.clear()
        # A cached result from a now-disconnected database shouldn't be
        # propose-fixable -- the frontend already hides the report on
        # disconnect, this just keeps server-side state consistent with that.
        last_result_store.clear()

    @app.get("/api/views", response_model=ViewsResponse)
    def get_views(
        store: SessionStore = Depends(get_session_store),
        list_views_fn: ListViewsFn = Depends(get_list_views_fn),
    ) -> ViewsResponse:
        params = _require_connection(store)
        try:
            views = list_views_fn(**_conn_kwargs(params))
        except DBCaptureError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return ViewsResponse(
            views=[
                ViewItem(
                    schema_name=v.schema_name,
                    view_name=v.view_name,
                    qualified_name=v.qualified_name,
                    select_body=v.select_body,
                )
                for v in views
            ]
        )

    @app.post("/api/query", response_model=QueryResponse)
    def run_query(
        body: QueryRequest,
        store: SessionStore = Depends(get_session_store),
        last_result_store: LastResultStore = Depends(get_last_result_store),
        capture_fn: CaptureFn = Depends(get_capture_fn),
        generate_fn: Callable[..., dict] = Depends(get_generate_fn),
    ) -> QueryResponse:
        params = _require_connection(store)
        try:
            xml = capture_fn(**_conn_kwargs(params), query=body.query)
        except QueryValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except DBCaptureError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        try:
            plan = parse_plan_xml(
                xml,
                plan_source=PlanSource.ACTUAL,
                object_type=ObjectType.ADHOC_QUERY,
                database_name=params.database,
                captured_at=datetime.now(timezone.utc),
                redact=body.redact,
            )
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to parse execution plan XML: {exc}") from exc

        findings = evaluate(plan)
        summary = summarize_plan(plan)
        last_result_store.set(LastResult(plan_summary=summary, findings=findings))

        narration: Optional[Narration] = None
        if body.narrate:
            client = _make_ollama_client(generate_fn, body.ollama_timeout_s)
            narration = get_narration(findings, summary, model=body.model, client=client)

        return _to_query_response(summary, findings, narration)

    @app.post("/api/propose-fix", response_model=ProposeFixResponse)
    def propose_fix(
        body: ProposeFixRequest,
        last_result_store: LastResultStore = Depends(get_last_result_store),
        generate_fn: Callable[..., dict] = Depends(get_generate_fn),
    ) -> ProposeFixResponse:
        result = _require_last_result(last_result_store)
        client = _make_ollama_client(generate_fn, body.ollama_timeout_s)
        proposal = propose_fixes(result.findings, result.plan_summary, model=body.model, client=client)
        return _to_propose_fix_response(proposal)

    # Mounted last so the catch-all static route doesn't shadow /api/*.
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app
