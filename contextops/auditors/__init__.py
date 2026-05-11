"""Auditor framework: Finding dataclass + Auditor protocol + registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..session import Session


# FinOps-style category labels. Short, headline-friendly, and stable enough
# that users can argue about them on Twitter without ambiguity.
class Category:
    ZOMBIE = "Zombie resources"
    RIGHTSIZING = "Rightsizing"
    OVERPROVISIONING = "Overprovisioning"
    RESERVED_CAPACITY = "Reserved capacity"
    WASTE_AVOIDANCE = "Waste avoidance"


@dataclass
class Finding:
    """One waste hit produced by an auditor."""

    auditor: str            # machine name, e.g. "repeated_file_reads"
    title: str              # human-readable category, e.g. "Repeated file reads"
    category: str           # FinOps category (see Category constants)
    wasted_tokens: int
    wasted_dollars: float
    recommendation: str
    methodology: str        # one-line "how we detected this", for transparency
    evidence: list[str] = field(default_factory=list)
    fix_hint: str | None = None


@runtime_checkable
class Auditor(Protocol):
    name: str
    title: str
    category: str

    def run(self, session: Session) -> list[Finding]: ...


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def all_auditors() -> list[Auditor]:
    """Return all built-in auditors in display order (high-impact first)."""
    from .repeated_file_reads import RepeatedFileReads
    from .oversized_file_reads import OversizedFileReads
    from .bloated_claude_md import BloatedClaudeMd
    from .unused_mcp_tools import UnusedMcpTools
    from .redundant_exploration import RedundantExploration
    from .failed_then_retried import FailedThenRetried
    from .oversized_tool_outputs import OversizedToolOutputs
    from .duplicate_bash_runs import DuplicateBashRuns
    from .large_image_uploads import LargeImageUploads
    from .prompt_context_stuffing import PromptContextStuffing

    return [
        RepeatedFileReads(),
        OversizedFileReads(),
        BloatedClaudeMd(),
        UnusedMcpTools(),
        RedundantExploration(),
        FailedThenRetried(),
        OversizedToolOutputs(),
        DuplicateBashRuns(),
        LargeImageUploads(),
        PromptContextStuffing(),
    ]
