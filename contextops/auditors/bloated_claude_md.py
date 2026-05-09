"""Auditor 5 — bloated CLAUDE.md (FinOps: reserved capacity / rightsizing)."""

from __future__ import annotations

import re
from pathlib import Path

from . import Auditor, Category, Finding
from ..pricing import Pricing, estimate_tokens
from ..session import Session


SIZE_THRESHOLD_TOKENS = 2_000


class BloatedClaudeMd:
    name = "bloated_claude_md"
    title = "Bloated CLAUDE.md"
    category = Category.RESERVED_CAPACITY

    def run(self, session: Session) -> list[Finding]:
        path = _find_claude_md(session)
        if not path:
            return []

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        tokens = estimate_tokens(text)
        if tokens < SIZE_THRESHOLD_TOKENS:
            return []

        pricing = Pricing.for_model(session.model)
        turns = max(1, len(session.assistant_turns))

        # If the session used prompt caching at all, treat half of the
        # CLAUDE.md repetitions as already covered by reads of the cached
        # prefix. This avoids the embarrassing case where we tell users to
        # trim something Anthropic already discounted to ~1.5¢ on the dollar.
        usage = session.total_usage
        cache_hits = usage.cache_read_input_tokens
        cache_writes = usage.cache_creation_input_tokens
        is_cached = (cache_hits + cache_writes) > 0

        per_turn_tokens = tokens
        repetition_factor = turns if not is_cached else max(1, turns // 2)
        wasted_tokens = per_turn_tokens * repetition_factor

        # Trimmable portion = sections that are oversized relative to the median.
        sections = _section_breakdown(text)
        trim_candidates = [s for s in sections if s.tokens > tokens // 4]
        trim_total = sum(s.tokens for s in trim_candidates)
        trim_pct = int(round(100 * trim_total / max(1, tokens)))

        # Apply pricing. Cached portions are billed at cache-read rate.
        if is_cached:
            dollars = pricing.dollars(
                input_tokens=per_turn_tokens,
                cache_read_tokens=wasted_tokens - per_turn_tokens,
            )
        else:
            dollars = pricing.dollars(input_tokens=wasted_tokens)

        if trim_candidates:
            section_blurb = (
                f"Top sections by size: "
                + ", ".join(
                    f"[italic]{s.heading}[/italic] (~{s.tokens:,}t)"
                    for s in trim_candidates[:3]
                )
                + f" — together ~{trim_pct}% of the file."
            )
        else:
            section_blurb = "No single section dominates; consider splitting into a referenced doc."

        cache_blurb = (
            "Prompt caching looks active, but the prefix is still re-billed "
            "at cache-read rate every turn. "
            if is_cached
            else "Prompt caching does not appear active for this session. "
        )

        finding = Finding(
            auditor=self.name,
            title=self.title,
            category=self.category,
            wasted_tokens=wasted_tokens,
            wasted_dollars=dollars,
            recommendation=(
                f"Your CLAUDE.md is {tokens:,} tokens and was sent on every "
                f"one of your {turns} turns this session "
                f"(~{wasted_tokens:,} tokens, ${dollars:0.2f}). "
                + cache_blurb
                + section_blurb
            ),
            methodology=(
                "Counted CLAUDE.md size (~4 chars/token), multiplied by the "
                "session's assistant-turn count, halved if prompt caching was "
                "observed in any turn's usage."
            ),
            evidence=[
                f"path: {path}",
                f"size: {tokens:,} tokens; turns: {turns}; "
                f"caching: {'on' if is_cached else 'off'}",
            ],
        )
        return [finding]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _Section:
    __slots__ = ("heading", "tokens")

    def __init__(self, heading: str, tokens: int) -> None:
        self.heading = heading
        self.tokens = tokens


def _find_claude_md(session: Session) -> Path | None:
    """Try the session's cwd, then the package's own cwd."""
    candidates: list[Path] = []
    if session.cwd:
        candidates.append(Path(session.cwd) / "CLAUDE.md")
    candidates.append(Path.cwd() / "CLAUDE.md")
    for c in candidates:
        if c.is_file():
            return c
    return None


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


def _section_breakdown(text: str) -> list[_Section]:
    """Return sections largest-first, keyed by their heading."""
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return []
    out: list[_Section] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        out.append(_Section(heading=m.group(2).strip(), tokens=estimate_tokens(body)))
    out.sort(key=lambda s: s.tokens, reverse=True)
    return out
