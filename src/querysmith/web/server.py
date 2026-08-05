"""`querysmith-web` entry point: runs the local web UI via uvicorn (see
design-notes/execution-plan-web-ui.md). Binds to localhost by default --
this is a single-local-user tool with no auth layer, not meant to be
exposed beyond the machine it runs on.
"""

from __future__ import annotations

import argparse
from typing import Optional

import uvicorn

__all__ = ["main"]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8420


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="querysmith-web", description="Run the QuerySmith local web UI.")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Host to bind (default: {DEFAULT_HOST!r})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port to bind (default: {DEFAULT_PORT})")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for local development")
    args = parser.parse_args(argv)

    uvicorn.run(
        "querysmith.web.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
