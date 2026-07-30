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
