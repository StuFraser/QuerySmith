"""`querysmith` CLI: connect live to SQL Server, capture an execution plan,
and print the Tier 0 / Tier 1 analysis (see design-notes/execution-plan-agent-scope.md).
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Callable, Optional

from querysmith.adapters.sqlserver import parse_plan_xml
from querysmith.db import DBCaptureError, QueryValidationError, capture_plan_xml
from querysmith.db.connection import DEFAULT_ODBC_DRIVER
from querysmith.ir.models import ObjectType, PlanSource
from querysmith.narration import DEFAULT_MODEL, Narration, PlanSummary, get_narration, summarize_plan
from querysmith.narration.ollama_client import generate_json
from querysmith.rules import Finding, evaluate

__all__ = ["main", "run", "format_report"]

PASSWORD_ENV_VAR = "QUERYSMITH_DB_PASSWORD"

CaptureFn = Callable[..., str]
GenerateFn = Callable[[str, str], dict]

_PRIVILEGED_USERNAMES = {"sa", "admin", "administrator", "root"}

EXIT_OK = 0
EXIT_CAPTURE_ERROR = 1
EXIT_USAGE_ERROR = 2


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return run(args)


def run(
    args: argparse.Namespace,
    *,
    capture_fn: CaptureFn = capture_plan_xml,
    narration_client: Optional[GenerateFn] = None,
) -> int:
    password = os.environ.get(PASSWORD_ENV_VAR)
    if not password:
        print(
            f"Error: {PASSWORD_ENV_VAR} environment variable is not set. "
            "Refusing to proceed without a password (never pass it as a flag).",
            file=sys.stderr,
        )
        return EXIT_USAGE_ERROR

    reminder = _read_only_reminder(args.user)
    if reminder:
        print(reminder, file=sys.stderr)

    try:
        xml = capture_fn(
            server=args.server,
            database=args.database,
            user=args.user,
            password=password,
            query=args.query,
            driver=args.driver,
            trust_server_certificate=args.trust_server_certificate,
            timeout_s=args.timeout,
        )
    except QueryValidationError as exc:
        print(f"Error: query validation failed: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    except DBCaptureError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_CAPTURE_ERROR

    try:
        plan = parse_plan_xml(
            xml,
            plan_source=PlanSource.ACTUAL,
            object_type=ObjectType.ADHOC_QUERY,
            database_name=args.database,
            captured_at=datetime.now(timezone.utc),
        )
    except ValueError as exc:
        print(f"Error: failed to parse execution plan XML: {exc}", file=sys.stderr)
        return EXIT_CAPTURE_ERROR

    findings = evaluate(plan)
    summary = summarize_plan(plan)

    narration: Optional[Narration] = None
    if args.narrate:
        client = narration_client if narration_client is not None else _make_ollama_client(args.ollama_timeout)
        narration = get_narration(findings, summary, model=args.model, client=client)

    print(format_report(summary, findings, narration))
    return EXIT_OK


def _make_ollama_client(timeout_s: float) -> GenerateFn:
    def client(prompt: str, model: str) -> dict:
        return generate_json(prompt, model, timeout_s=timeout_s)

    return client


def _read_only_reminder(user: str) -> Optional[str]:
    if user.strip().lower() in _PRIVILEGED_USERNAMES:
        return (
            f"Reminder: '{user}' looks like a privileged account. QuerySmith only "
            "issues read-only SELECT/STATISTICS XML statements, but for real "
            "defense-in-depth (the DB-level read-only role the scope doc calls "
            "the actual security boundary), connect with a login scoped to "
            "db_datareader + SHOWPLAN instead."
        )
    return None


def _fmt_number(value: Optional[float]) -> str:
    return f"{value:,.2f}" if value is not None else "n/a"


def _fmt_int(value: Optional[int]) -> str:
    return f"{value:,}" if value is not None else "n/a"


def format_report(summary: PlanSummary, findings: list[Finding], narration: Optional[Narration]) -> str:
    lines: list[str] = []
    lines.append("QuerySmith Execution Plan Report")
    lines.append("=" * 33)
    engine_line = summary.engine
    if summary.engine_version:
        engine_line += f" ({summary.engine_version})"
    lines.append(f"Engine:          {engine_line}")
    lines.append(f"Database:        {summary.database_name or 'unknown'}")
    lines.append(f"Object type:     {summary.object_type}")
    lines.append(f"Statement type:  {summary.statement_type}")
    lines.append("Statement text:")
    for line in summary.statement_text.splitlines() or [""]:
        lines.append(f"    {line}")
    lines.append("")
    lines.append("Plan totals:")
    lines.append(f"    Estimated cost:   {_fmt_number(summary.total_estimated_cost)}")
    lines.append(f"    Actual duration:  {_fmt_number(summary.total_actual_duration_ms)} ms")
    lines.append(f"    Actual rows:      {_fmt_int(summary.total_actual_rows)}")
    lines.append(f"    Operator count:   {summary.operator_count}")
    lines.append("")

    header = f"Findings ({len(findings)})"
    lines.append(header)
    lines.append("-" * len(header))
    if not findings:
        lines.append("No issues found by the Tier 0 rules engine.")
    else:
        narration_by_index = {i: fn for i, fn in enumerate(narration.findings)} if narration else {}
        for i, finding in enumerate(findings):
            lines.append(f"[{i + 1}] {finding.severity.value.upper():<8} {finding.rule_id}")
            lines.append(f"    {finding.summary}")
            fn = narration_by_index.get(i)
            if fn is not None:
                lines.append(f"    Explanation: {fn.explanation}")
            if finding.suggested_fix:
                fix_text, fix_label = finding.suggested_fix, "Suggested fix:"
            elif fn is not None and fn.suggested_fix:
                fix_text, fix_label = fn.suggested_fix, "Suggested fix (model):"
            else:
                fix_text = None
            if fix_text is not None:
                lines.append(f"    {fix_label}")
                for fix_line in fix_text.splitlines():
                    lines.append(f"        {fix_line}")
            lines.append("")

    lines.append("Overview")
    lines.append("-" * 8)
    if narration is not None:
        lines.append(narration.overview)
        if narration.degraded:
            lines.append(f"[Tier 1 narration degraded: {narration.degraded_reason}]")
    else:
        lines.append("Tier 1 narration disabled (--no-narrate). Showing Tier 0 findings only.")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="querysmith",
        description="Connect to SQL Server, capture an execution plan, and analyze it.",
    )
    parser.add_argument("--server", required=True, help="SQL Server hostname, optionally host,port (e.g. localhost,1433)")
    parser.add_argument("--database", required=True, help="Target database name")
    parser.add_argument(
        "--user",
        required=True,
        help="SQL Server login username (SQL authentication only -- Windows/integrated auth is not supported)",
    )
    parser.add_argument(
        "--query",
        required=True,
        help='Ad-hoc SELECT query to capture a plan for (e.g. "SELECT * FROM dbo.MyView"). '
        "Must parse as a single read-only SELECT statement -- rejected otherwise.",
    )
    parser.add_argument(
        "--driver",
        default=DEFAULT_ODBC_DRIVER,
        help=f"ODBC driver name as registered in odbcinst.ini (default: {DEFAULT_ODBC_DRIVER!r})",
    )
    parser.add_argument(
        "--trust-server-certificate",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Trust the server's TLS certificate without validation (needed for self-signed certs on local/dev instances)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Login and query timeout in seconds for the SQL Server connection (default: 60)",
    )
    parser.add_argument(
        "--narrate",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run Tier 1 local-model narration (default: on). Disable for fast Tier 0-only output.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model name for Tier 1 narration (default: {DEFAULT_MODEL!r})")
    parser.add_argument(
        "--ollama-timeout",
        type=float,
        default=600.0,
        help="Timeout in seconds for each Ollama narration request. Local CPU-only inference can take "
        "minutes -- the library's own default (30s) is too short for real use. (default: 600)",
    )
    return parser


if __name__ == "__main__":
    sys.exit(main())
