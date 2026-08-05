"""In-memory connection session for the local web UI (see
design-notes/execution-plan-web-ui.md). Single-process, single-active-
connection store -- confirmed single-user, one-client-at-a-time usage, so a
module-level singleton guarded by a lock is sufficient; no session
IDs/cookies/auth. The lock exists because Starlette runs sync `def` routes
in a threadpool, so even one browser tab can produce concurrent requests
(e.g. a double-clicked button), not because this supports multiple users.

Password handling: held in-process memory only, for process lifetime or
until `clear()` is called. Never persisted to disk, never included in
`ConnectionParams.__repr__` (so it can't leak via an accidental log call or
an unhandled-exception traceback), and callers must never put it in a
response body.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional

__all__ = ["ConnectionParams", "SessionStore", "get_session_store", "NotConnectedError"]


class NotConnectedError(Exception):
    """Raised by SessionStore.get() when there is no active connection (no
    prior successful POST /api/connection, or it was since cleared)."""


@dataclass(frozen=True)
class ConnectionParams:
    server: str
    database: str
    user: str
    password: str
    driver: str
    trust_server_certificate: bool
    timeout_s: float

    def __repr__(self) -> str:
        return (
            f"ConnectionParams(server={self.server!r}, database={self.database!r}, "
            f"user={self.user!r}, driver={self.driver!r})"
        )


class SessionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._params: Optional[ConnectionParams] = None

    def set(self, params: ConnectionParams) -> None:
        with self._lock:
            self._params = params

    def get(self) -> ConnectionParams:
        with self._lock:
            if self._params is None:
                raise NotConnectedError("No active connection. POST /api/connection first.")
            return self._params

    def clear(self) -> None:
        with self._lock:
            self._params = None

    def is_connected(self) -> bool:
        with self._lock:
            return self._params is not None


_store = SessionStore()


def get_session_store() -> SessionStore:
    """FastAPI dependency accessor. Tests override this via
    app.dependency_overrides[get_session_store] to inject a fresh
    SessionStore instead of sharing the module-level singleton."""
    return _store
