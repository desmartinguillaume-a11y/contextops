"""Auditor — prompt context stuffing (FinOps: overprovisioning)."""
from __future__ import annotations

import logging
import re
from collections import Counter

from . import Category, Finding
from ..pricing import Pricing, estimate_tokens
from ..session import Session

log = logging.getLogger(__name__)

STUFFING_THRESHOLD = 5_000  # tokens
_TS_PATTERN = re.compile(r'(\d{2}:\d{2}:\d{2}|\d{4}-\d{2}-\d{2})')
_PREFIX_LEN = 4
_PREFIX_RATIO = 0.40


def _detect_signal(text: str) -> str | None:
    """Return signal name if a structural stuffing signal is found, else None."""
    # 1. Stack trace keywords
    if "Traceback" in text or "Exception:" in text or "Error:" in text:
        return "stack_trace"

    # 2. Timestamp sequence (>=3 lines beginning with timestamp pattern)
    lines = text.splitlines()
    ts_count = sum(
        1 for line in lines
        if _TS_PATTERN.match(line.lstrip())
    )
    if ts_count >= 3:
        return "timestamp_sequence"

    # 3. High line-prefix repetition (>40% of non-empty lines share first 4 chars)
    non_empty = [line.lstrip() for line in lines if line.strip()]
    if len(non_empty) >= 5:  # need enough lines for a meaningful ratio
        prefix_counts = Counter(line[:_PREFIX_LEN] for line in non_empty)
        top_count = prefix_counts.most_common(1)[0][1]
        if top_count / len(non_empty) > _PREFIX_RATIO:
            return "prefix_repetition"

    return None


class PromptContextStuffing:
    name = "prompt_context_stuffing"
    title = "Prompt context stuffing"
    category = Category.OVERPROVISIONING

    def run(self, session: Session) -> list[Finding]:
        pricing = Pricing.for_model(session.model)
        findings: list[Finding] = []

        for turn in session.user_turns:
            try:
                if turn.tool_results:
                    continue  # tool-result delivery turn
                text = turn.text or ""
                tokens = estimate_tokens(text)
                if tokens <= STUFFING_THRESHOLD:
                    continue
                signal = _detect_signal(text)
                if signal is None:
                    continue
                dollars = pricing.dollars(input_tokens=tokens)
                findings.append(
                    Finding(
                        auditor=self.name,
                        title=self.title,
                        category=self.category,
                        wasted_tokens=tokens,
                        wasted_dollars=dollars,
                        recommendation=(
                            f"User turn {turn.index} contains "
                            f"[bold]{tokens:,} tokens[/bold] "
                            f"(${dollars:.4f}) with a [bold]{signal}[/bold] "
                            f"signal — likely a pasted blob. "
                            f"This degrades model accuracy via 'lost in the middle' effect."
                        ),
                        methodology=(
                            "Estimated tokens per user turn; for turns "
                            f"> {STUFFING_THRESHOLD:,} tokens, checked for "
                            "structural stuffing signals (stack trace, timestamps, "
                            "high line-prefix repetition)."
                        ),
                        evidence=[
                            f"turn {turn.index}: {tokens:,} tokens, "
                            f"signal={signal}"
                        ],
                        fix_hint=(
                            "Write this content to a file and use the Read tool "
                            "to reference it, or paste only the relevant excerpt "
                            "(< 200 lines)."
                        ),
                    )
                )
            except Exception:
                log.debug(
                    "prompt_context_stuffing: error processing turn %s",
                    getattr(turn, "index", "?"),
                    exc_info=True,
                )

        findings.sort(key=lambda f: f.wasted_tokens, reverse=True)
        return findings
