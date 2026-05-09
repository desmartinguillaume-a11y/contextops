"""Auditor 1 — repeated file reads (FinOps: zombie resources)."""

from __future__ import annotations

from collections import defaultdict

from . import Auditor, Category, Finding
from ..pricing import Pricing, estimate_tokens
from ..session import Session


class RepeatedFileReads:
    name = "repeated_file_reads"
    title = "Repeated file reads"
    category = Category.ZOMBIE

    def run(self, session: Session) -> list[Finding]:
        pricing = Pricing.for_model(session.model)

        # Per-path timeline of (turn_index, kind, content). kind in {"read","mutate"}.
        timeline: dict[str, list[tuple[int, str, str]]] = defaultdict(list)

        for tu in session.tool_calls():
            path = _path_arg(tu.input)
            if not path:
                continue
            if tu.name == "Read":
                result = session.result_for(tu.id)
                content = result.content if result else ""
                timeline[path].append((tu.turn_index, "read", content))
            elif tu.name in ("Edit", "Write", "MultiEdit"):
                timeline[path].append((tu.turn_index, "mutate", ""))

        findings: list[Finding] = []
        for path, events in timeline.items():
            reads = [e for e in events if e[1] == "read"]
            if len(reads) < 2:
                continue

            # Walk events in order. Each "read" after a previous read with no
            # intervening "mutate" is redundant. The redundant cost is the
            # token count of the redundant read's content.
            wasted_tokens = 0
            redundant_count = 0
            had_clean_read = False
            for turn_idx, kind, content in events:
                if kind == "mutate":
                    had_clean_read = False
                    continue
                if had_clean_read:
                    wasted_tokens += estimate_tokens(content)
                    redundant_count += 1
                else:
                    had_clean_read = True

            if redundant_count == 0:
                continue

            dollars = pricing.dollars(input_tokens=wasted_tokens)
            findings.append(
                Finding(
                    auditor=self.name,
                    title=self.title,
                    category=self.category,
                    wasted_tokens=wasted_tokens,
                    wasted_dollars=dollars,
                    recommendation=(
                        f"You read [bold]{_short(path)}[/bold] {len(reads)} times "
                        f"this session "
                        f"(~{wasted_tokens:,} tokens, ${dollars:0.2f}). Once a "
                        f"file is in context, ask Claude to recall it instead "
                        f"of re-reading. Frequently-referenced files belong "
                        f"in CLAUDE.md."
                    ),
                    methodology=(
                        "Grouped Read tool calls by absolute path; "
                        "counted reads with no intervening Edit/Write as redundant."
                    ),
                    evidence=[
                        f"{path}: {len(reads)} reads, "
                        f"{redundant_count} redundant"
                    ],
                )
            )

        findings.sort(key=lambda f: f.wasted_tokens, reverse=True)
        return findings


def _path_arg(d: dict) -> str | None:
    p = d.get("file_path") or d.get("path")
    return str(p) if p else None


def _short(path: str, max_len: int = 48) -> str:
    if len(path) <= max_len:
        return path
    return "…" + path[-(max_len - 1):]
