"""Auditor 3 — redundant exploration (FinOps: zombie resources).

Repeated `LS` / `Glob` / `find` invocations on overlapping target paths.
The directory structure rarely changes mid-session; the second walk is
just paying again for stale information.
"""

from __future__ import annotations

import os
from collections import defaultdict

from . import Auditor, Category, Finding
from ..pricing import Pricing, estimate_tokens
from ..session import Session


EXPLORATION_TOOLS = {"LS", "Glob"}
# Bash counts only when the command is plainly directory exploration.
_BASH_EXPLORE = ("ls ", "ls\n", "ls\t", "find ", "tree ")


class RedundantExploration:
    name = "redundant_exploration"
    title = "Redundant directory exploration"
    category = Category.ZOMBIE

    def run(self, session: Session) -> list[Finding]:
        pricing = Pricing.for_model(session.model)
        # Group by normalized target. Each entry stores (turn_index, tool_use_id).
        groups: dict[str, list[tuple[int, str, str]]] = defaultdict(list)

        for tu in session.tool_calls():
            target = _target(tu.name, tu.input)
            if not target:
                continue
            groups[target].append((tu.turn_index, tu.id, tu.name))

        findings: list[Finding] = []
        for target, calls in groups.items():
            if len(calls) < 2:
                continue
            # Cost of the redundant ones = output size of every call after the first.
            redundant = calls[1:]
            wasted_tokens = 0
            for _idx, tool_use_id, _name in redundant:
                result = session.result_for(tool_use_id)
                wasted_tokens += estimate_tokens(result.content if result else "")
            if wasted_tokens == 0:
                # No cost to flag (the call returned nothing). Skip.
                continue

            dollars = pricing.dollars(input_tokens=wasted_tokens)
            tools = sorted({n for _, _, n in calls})
            findings.append(
                Finding(
                    auditor=self.name,
                    title=self.title,
                    category=self.category,
                    wasted_tokens=wasted_tokens,
                    wasted_dollars=dollars,
                    recommendation=(
                        f"You ran {'/'.join(tools)} on "
                        f"[bold]{target}[/bold] {len(calls)} times "
                        f"(~{wasted_tokens:,} tokens, ${dollars:0.2f}). The "
                        f"directory structure rarely changes mid-session — "
                        f"Claude can recall it from the first call."
                    ),
                    methodology=(
                        "Grouped LS/Glob/find calls by normalized target path; "
                        "treated calls after the first on the same target as redundant."
                    ),
                    evidence=[f"{target}: {len(calls)} calls via {'/'.join(tools)}"],
                )
            )

        findings.sort(key=lambda f: f.wasted_tokens, reverse=True)
        return findings


def _target(tool_name: str, args: dict) -> str | None:
    if tool_name == "LS":
        p = args.get("path")
        return _norm(p) if p else None
    if tool_name == "Glob":
        pat = args.get("pattern") or ""
        path = args.get("path") or ""
        if not pat:
            return None
        return f"{_norm(path)}::{pat}" if path else f"::{pat}"
    if tool_name == "Bash":
        cmd = (args.get("command") or "").strip()
        if not cmd:
            return None
        low = cmd.lower()
        if not (low.startswith(_BASH_EXPLORE) or " ls " in (" " + low) or low == "ls"):
            return None
        # Crude path extractor: take the last whitespace-separated argument
        # that looks like a path. Good enough for v0 heuristics.
        parts = cmd.split()
        for tok in reversed(parts):
            if tok.startswith("/") or tok.startswith("./") or tok.startswith("~"):
                return _norm(tok)
        return _norm(parts[0])
    return None


def _norm(p: str | None) -> str:
    if not p:
        return ""
    return os.path.normpath(os.path.expanduser(p)).rstrip("/")
