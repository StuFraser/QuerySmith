"""Tier 0 output structure (see design-notes/execution-plan-agent-scope.md)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from querysmith.ir.models import Severity


@dataclass
class Finding:
    rule_id: str
    severity: Severity
    operator_id: Optional[str]
    summary: str
    detail: str
    # Set only when Tier 0 can derive a fix mechanically from data it already
    # has (currently: missing_index_available's CREATE INDEX script). Tier 0
    # never guesses a fix for findings where the right remediation depends on
    # the actual query -- that's Tier 1's job (FindingNarration.suggested_fix).
    suggested_fix: Optional[str] = None
