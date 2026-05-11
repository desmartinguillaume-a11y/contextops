"""Auditor — duplicate bash runs (FinOps: zombie resources). Stub for BOLT-03."""

from __future__ import annotations

from . import Auditor, Category, Finding
from ..session import Session


class DuplicateBashRuns:
    name = "duplicate_bash_runs"
    title = "Duplicate bash runs"
    category = Category.ZOMBIE

    def run(self, session: Session) -> list[Finding]:
        return []
