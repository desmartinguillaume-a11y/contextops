"""Auditor — prompt context stuffing (FinOps: overprovisioning). Stub for BOLT-05."""

from __future__ import annotations

from . import Auditor, Category, Finding
from ..session import Session


class PromptContextStuffing:
    name = "prompt_context_stuffing"
    title = "Prompt context stuffing"
    category = Category.OVERPROVISIONING

    def run(self, session: Session) -> list[Finding]:
        return []
