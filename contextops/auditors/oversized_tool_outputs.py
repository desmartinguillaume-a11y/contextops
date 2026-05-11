"""Auditor — oversized tool outputs (FinOps: rightsizing). Stub for BOLT-02."""

from __future__ import annotations

from . import Auditor, Category, Finding
from ..session import Session


class OversizedToolOutputs:
    name = "oversized_tool_outputs"
    title = "Oversized tool outputs"
    category = Category.RIGHTSIZING

    def run(self, session: Session) -> list[Finding]:
        return []
