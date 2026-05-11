"""Auditor — oversized tool outputs (FinOps: rightsizing)."""
from __future__ import annotations

from . import Category, Finding
from ..pricing import Pricing, estimate_tokens
from ..session import Session

BASH_THRESHOLD = 2_000   # tokens
OTHER_THRESHOLD = 5_000  # tokens
_SNIPPET_LEN = 120


class OversizedToolOutputs:
    name = "oversized_tool_outputs"
    title = "Oversized tool outputs"
    category = Category.RIGHTSIZING

    def run(self, session: Session) -> list[Finding]:
        pricing = Pricing.for_model(session.model)
        findings: list[Finding] = []

        for tu in session.tool_calls():
            result = session.result_for(tu.id)
            if result is None:
                continue
            content = result.content or ""
            tokens = estimate_tokens(content)
            threshold = BASH_THRESHOLD if tu.name == "Bash" else OTHER_THRESHOLD
            if tokens <= threshold:
                continue

            snippet = content[:_SNIPPET_LEN]
            dollars = pricing.dollars(input_tokens=tokens)
            if tu.name == "Bash":
                fix_hint = (
                    "Truncate bash output to the first N lines, "
                    "or use grep/jq to filter before capture."
                )
            else:
                fix_hint = (
                    "Read only the relevant file section using offset+limit, "
                    "or summarise with a tool wrapper."
                )
            findings.append(
                Finding(
                    auditor=self.name,
                    title=self.title,
                    category=self.category,
                    wasted_tokens=tokens,
                    wasted_dollars=dollars,
                    recommendation=(
                        f"Tool [bold]{tu.name}[/bold] returned "
                        f"[bold]{tokens:,} tokens[/bold] "
                        f"(${dollars:.4f}) — above the "
                        f"{'2,000' if tu.name == 'Bash' else '5,000'}-token "
                        f"threshold. Input: {snippet!r:.80}"
                    ),
                    methodology=(
                        "Compared estimate_tokens(result.content) to "
                        "per-tool threshold (Bash: 2,000; other: 5,000)."
                    ),
                    evidence=[
                        f"{tu.name}: {tokens:,} tokens "
                        f"(input snippet: {snippet!r})"
                    ],
                    fix_hint=fix_hint,
                )
            )

        findings.sort(key=lambda f: f.wasted_tokens, reverse=True)
        return findings
