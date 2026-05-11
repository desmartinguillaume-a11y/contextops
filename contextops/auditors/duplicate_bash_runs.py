"""Auditor — duplicate bash runs (FinOps: zombie resources)."""
from __future__ import annotations

import logging

from . import Category, Finding
from ..pricing import Pricing, estimate_tokens
from ..session import Session

log = logging.getLogger(__name__)

MUTATION_MARKERS = (">", ">>", "rm ", "mv ", "cp ", "mkdir",
                    "git commit", "git push", "sed -i", "tee ")


def _normalize(cmd: str) -> str:
    return " ".join(cmd.split())


def _is_mutation(cmd: str) -> bool:
    return any(m in cmd for m in MUTATION_MARKERS)


class DuplicateBashRuns:
    name = "duplicate_bash_runs"
    title = "Duplicate bash runs"
    category = Category.ZOMBIE

    def run(self, session: Session) -> list[Finding]:
        pricing = Pricing.for_model(session.model)

        # Per normalized command: list of (turn_index, raw_command, result_content)
        occurrences: dict[str, list[tuple[int, str, str]]] = {}
        # Track which commands are "reset" by an intervening mutation
        blocked: set[str] = set()

        bash_calls = list(session.tool_calls("Bash"))
        if not bash_calls:
            return []

        for tu in bash_calls:
            try:
                raw_cmd = tu.input.get("command", "")
            except Exception:
                log.debug("duplicate_bash_runs: skipping malformed ToolUse %s", tu.id)
                continue
            if not raw_cmd:
                log.debug("duplicate_bash_runs: empty command on ToolUse %s", tu.id)
                continue

            norm = _normalize(raw_cmd)
            result = session.result_for(tu.id)
            content = result.content if result else ""

            if _is_mutation(raw_cmd):
                # Reset all active tracked commands
                blocked.update(occurrences.keys())

            if norm in blocked:
                # This command was reset — start fresh
                blocked.discard(norm)
                occurrences[norm] = [(tu.turn_index, raw_cmd, content)]
            else:
                occurrences.setdefault(norm, [])
                occurrences[norm].append((tu.turn_index, raw_cmd, content))

        findings: list[Finding] = []
        for norm, hits in occurrences.items():
            if len(hits) < 2:
                continue
            last_content = hits[-1][2]
            wasted_tokens = estimate_tokens(last_content) if last_content else 0
            dollars = pricing.dollars(input_tokens=wasted_tokens)
            evidence = [f"turn {idx}: {cmd!r}" for idx, cmd, _ in hits]
            findings.append(
                Finding(
                    auditor=self.name,
                    title=self.title,
                    category=self.category,
                    wasted_tokens=wasted_tokens,
                    wasted_dollars=dollars,
                    recommendation=(
                        f"Command [bold]{norm!r}[/bold] was run "
                        f"[bold]{len(hits)} times[/bold] with no "
                        f"intervening state-mutating command "
                        f"(~{wasted_tokens:,} tokens, ${dollars:.4f} waste)."
                    ),
                    methodology=(
                        "Collected all Bash ToolUse calls; "
                        "normalized whitespace; flagged commands "
                        "appearing 2+ times with no mutation in between."
                    ),
                    evidence=evidence,
                    fix_hint=(
                        "Cache the result of this read-only command in a "
                        "variable or file and reuse it instead of re-executing."
                    ),
                )
            )

        findings.sort(key=lambda f: f.wasted_tokens, reverse=True)
        return findings
