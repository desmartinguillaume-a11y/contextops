"""Auditor 6 — failed then retried (FinOps: waste avoidance)."""

from __future__ import annotations

from difflib import SequenceMatcher

from . import Auditor, Category, Finding
from ..pricing import Pricing, estimate_tokens
from ..session import Session


SIMILARITY_THRESHOLD = 0.8


class FailedThenRetried:
    name = "failed_then_retried"
    title = "Failed-then-retried tool calls"
    category = Category.WASTE_AVOIDANCE

    def run(self, session: Session) -> list[Finding]:
        pricing = Pricing.for_model(session.model)
        calls = session.tool_calls()
        retried = 0
        wasted_tokens = 0
        examples: list[str] = []

        for prev, nxt in zip(calls, calls[1:]):
            if prev.name != nxt.name:
                continue
            prev_result = session.result_for(prev.id)
            if not prev_result or not prev_result.is_error:
                continue
            sim = _similarity(prev.input, nxt.input)
            if sim < SIMILARITY_THRESHOLD:
                continue

            retried += 1
            wasted_tokens += estimate_tokens(prev_result.content)
            if len(examples) < 3:
                examples.append(
                    f"{prev.name}: error then retried "
                    f"(similarity {sim:0.2f}) — turn {prev.turn_index}"
                )

        if retried == 0:
            return []

        dollars = pricing.dollars(input_tokens=wasted_tokens)
        return [
            Finding(
                auditor=self.name,
                title=self.title,
                category=self.category,
                wasted_tokens=wasted_tokens,
                wasted_dollars=dollars,
                recommendation=(
                    f"{retried} tool call{'s' if retried != 1 else ''} failed "
                    f"and {'were' if retried != 1 else 'was'} retried "
                    f"~unchanged this session (~${dollars:0.2f} wasted). "
                    f"Have Claude inspect the environment "
                    f"(e.g. [cyan]which python[/cyan], [cyan]ls[/cyan]) "
                    f"before retrying a failed command."
                ),
                methodology=(
                    f"Found consecutive tool calls of the same name where the "
                    f"first returned is_error=true and the second's inputs "
                    f"matched at ≥{SIMILARITY_THRESHOLD:0.0%} by SequenceMatcher."
                ),
                evidence=examples,
            )
        ]


def _similarity(a: dict, b: dict) -> float:
    """Crude similarity over tool input dicts."""
    if a == b:
        return 1.0
    sa = _stringify(a)
    sb = _stringify(b)
    if not sa or not sb:
        return 0.0
    return SequenceMatcher(None, sa, sb).ratio()


def _stringify(d: dict) -> str:
    parts = []
    for k in sorted(d):
        v = d[k]
        parts.append(f"{k}={v}")
    return "\n".join(parts)
