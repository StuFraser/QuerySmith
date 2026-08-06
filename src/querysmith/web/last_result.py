"""In-memory store for the most recent /api/query result (see
design-notes/execution-plan-web-ui.md, "Propose Fix" two-step flow). Lets
POST /api/propose-fix reuse the plan summary and findings from the last
query without re-executing it against SQL Server -- fix proposals are a
pure narration-layer operation and never need to touch the database.

Same single-process, single-active-session posture as SessionStore (see
that module's docstring for the reasoning): no session IDs, one
lock-guarded slot, not a multi-tenant cache.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional

from querysmith.narration import PlanSummary
from querysmith.rules import Finding

__all__ = ["LastResult", "LastResultStore", "get_last_result_store", "NoResultAvailableError"]


class NoResultAvailableError(Exception):
    """Raised by LastResultStore.get() when there is no prior successful
    POST /api/query result to propose fixes for."""


@dataclass(frozen=True)
class LastResult:
    plan_summary: PlanSummary
    findings: list[Finding]


class LastResultStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._result: Optional[LastResult] = None

    def set(self, result: LastResult) -> None:
        with self._lock:
            self._result = result

    def get(self) -> LastResult:
        with self._lock:
            if self._result is None:
                raise NoResultAvailableError("No query has been run yet. POST /api/query first.")
            return self._result

    def clear(self) -> None:
        with self._lock:
            self._result = None


_store = LastResultStore()


def get_last_result_store() -> LastResultStore:
    """FastAPI dependency accessor. Tests override this via
    app.dependency_overrides[get_last_result_store] to inject a fresh
    LastResultStore instead of sharing the module-level singleton."""
    return _store
