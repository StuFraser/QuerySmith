"""Deterministic, parser-based validation that user-supplied query text is a
single read-only SELECT statement (see design-notes/execution-plan-agent-scope.md,
Security section: "Parser-based statement validation as a second opinion").
sqlglot parses into a real AST rather than pattern-matching keywords, so
comment-based obfuscation and stacked/multi-statement input are rejected by
construction, not blocklisted. Fails closed: any parse ambiguity or error is
a rejection, never a pass-through. Callers must never catch
QueryValidationError and fall back to sending the raw text anyway.
"""

from __future__ import annotations

import sqlglot
from sqlglot import expressions as exp
from sqlglot.errors import ParseError

__all__ = ["validate_select_only", "QueryValidationError", "DIALECT"]

# T-SQL only -- SQL Server is the only engine this pass connects to.
DIALECT = "tsql"


class QueryValidationError(Exception):
    """Raised when user-supplied query text fails to validate as exactly one
    read-only SELECT statement. Always raised before any network call."""


def validate_select_only(query_text: str) -> str:
    """Returns query_text unchanged on success -- never regenerates SQL from
    the AST (the AST only confirms shape; sending the original text avoids
    any drift from sqlglot's SQL generator)."""
    if not query_text or not query_text.strip():
        raise QueryValidationError("Query text is empty.")

    try:
        # error_level is passed explicitly rather than relying on sqlglot's
        # default, so strict-parse behavior can't silently drift across
        # sqlglot versions.
        parsed = sqlglot.parse(query_text, read=DIALECT, error_level=sqlglot.ErrorLevel.RAISE)
    except ParseError as exc:
        raise QueryValidationError(f"Query failed to parse: {exc}") from exc

    # A trailing/empty statement (e.g. "SELECT 1;;") parses to a None entry.
    statements = [s for s in parsed if s is not None]

    if len(statements) == 0:
        raise QueryValidationError("Query text contains no statements.")
    if len(statements) > 1:
        raise QueryValidationError(
            f"Query text must contain exactly one statement; found {len(statements)} "
            "(stacked/multi-statement input is rejected)."
        )

    statement = statements[0]
    if not isinstance(statement, exp.Select):
        raise QueryValidationError(
            f"Only SELECT statements are permitted; parsed statement type was {type(statement).__name__}."
        )

    return query_text
