"""Auditor 2 — oversized file reads (FinOps: rightsizing).

A `Read` is "oversized" when it pulls in a large body of text but only a
small fraction of its distinctive lines is referenced in subsequent
assistant turns.
"""

from __future__ import annotations

import re

from . import Auditor, Category, Finding
from ..pricing import Pricing, estimate_tokens
from ..session import Session, ToolUse


SIZE_THRESHOLD_TOKENS = 5_000
LOOKAHEAD_TURNS = 5
USAGE_THRESHOLD = 0.10  # 10% of distinctive lines must show up
SNIPPET_LEN = 30
MAX_SNIPPETS = 30


class OversizedFileReads:
    name = "oversized_file_reads"
    title = "Oversized file reads"
    category = Category.RIGHTSIZING

    def run(self, session: Session) -> list[Finding]:
        pricing = Pricing.for_model(session.model)
        findings: list[Finding] = []
        seen_paths: set[str] = set()

        reads = [tu for tu in session.tool_calls("Read")]
        for tu in reads:
            path_key = str(tu.input.get("file_path") or "")
            if path_key in seen_paths:
                continue
            result = session.result_for(tu.id)
            if not result or result.is_error:
                continue
            content = result.content or ""
            tokens = estimate_tokens(content)
            if tokens < SIZE_THRESHOLD_TOKENS:
                continue

            snippets = _distinctive_snippets(content)
            if not snippets:
                continue

            following = _following_assistant_text(session, tu, LOOKAHEAD_TURNS)
            if not following:
                # Read happened too late to evaluate. Skip rather than overflag.
                continue

            hit = sum(1 for s in snippets if s in following)
            ratio = hit / len(snippets)
            if ratio >= USAGE_THRESHOLD:
                continue

            wasted_fraction = 1.0 - ratio
            wasted_tokens = int(tokens * wasted_fraction)
            dollars = pricing.dollars(input_tokens=wasted_tokens)
            line_count = content.count("\n") + 1
            referenced_lines = max(1, int(line_count * ratio))
            path = tu.input.get("file_path", "<unknown>")

            seen_paths.add(path_key)
            findings.append(
                Finding(
                    auditor=self.name,
                    title=self.title,
                    category=self.category,
                    wasted_tokens=wasted_tokens,
                    wasted_dollars=dollars,
                    recommendation=(
                        f"You read all {line_count:,} lines of "
                        f"[bold]{_short(path)}[/bold] but only ~{referenced_lines} "
                        f"were referenced in the next {LOOKAHEAD_TURNS} turns "
                        f"(~{wasted_tokens:,} tokens, ${dollars:0.2f}). Use "
                        f"[cyan]Read[/cyan] with [italic]offset[/italic] and "
                        f"[italic]limit[/italic], or [cyan]Grep[/cyan] first "
                        f"to locate the relevant section."
                    ),
                    methodology=(
                        f"Sampled {len(snippets)} ~{SNIPPET_LEN}-char snippets "
                        f"from the read result; checked the next "
                        f"{LOOKAHEAD_TURNS} assistant turns for substring "
                        f"matches. Flagged when fewer than "
                        f"{int(USAGE_THRESHOLD * 100)}% appeared."
                    ),
                    evidence=[
                        f"{path}: {tokens:,} tokens read, "
                        f"{hit}/{len(snippets)} snippets referenced"
                    ],
                )
            )

        findings.sort(key=lambda f: f.wasted_tokens, reverse=True)
        return findings


_LINE_NOISE = re.compile(r"^[\s\W_0-9]*$")


def _distinctive_snippets(text: str) -> list[str]:
    """Pick up to MAX_SNIPPETS substrings that are plausibly unique."""
    lines = [ln for ln in text.splitlines() if not _LINE_NOISE.match(ln) and len(ln.strip()) >= SNIPPET_LEN]
    if not lines:
        return []
    if len(lines) <= MAX_SNIPPETS:
        sampled = lines
    else:
        step = len(lines) // MAX_SNIPPETS
        sampled = [lines[i] for i in range(0, len(lines), step)][:MAX_SNIPPETS]

    out: list[str] = []
    for ln in sampled:
        s = ln.strip()
        # Pick from the middle of the line; less likely to be common boilerplate.
        if len(s) <= SNIPPET_LEN:
            snip = s
        else:
            mid = (len(s) - SNIPPET_LEN) // 2
            snip = s[mid : mid + SNIPPET_LEN]
        if snip and snip not in out:
            out.append(snip)
    return out


def _following_assistant_text(session: Session, tu: ToolUse, n: int) -> str:
    found = 0
    parts: list[str] = []
    for t in session.assistant_turns:
        if t.index <= tu.turn_index:
            continue
        parts.append(t.text)
        found += 1
        if found >= n:
            break
    return "\n".join(parts)


def _short(path: str, max_len: int = 48) -> str:
    if len(path) <= max_len:
        return path
    return "…" + path[-(max_len - 1):]
