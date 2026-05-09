"""Auditor 4 — unused MCP tools (FinOps: overprovisioning)."""

from __future__ import annotations

from . import Auditor, Category, Finding
from ..pricing import Pricing
from ..session import Session


# Average serialized size of a Claude Code tool schema (name + JSON-Schema).
# Empirically ~150 input tokens per turn per tool. This is conservative.
TOKENS_PER_TOOL_PER_TURN = 150


class UnusedMcpTools:
    name = "unused_mcp_tools"
    title = "Unused MCP / deferred tools"
    category = Category.OVERPROVISIONING

    def run(self, session: Session) -> list[Finding]:
        pricing = Pricing.for_model(session.model)
        defined = list(session.tool_definitions)
        if not defined:
            return []

        called = {tu.name for tu in session.tool_calls()}
        unused = [t for t in defined if t not in called]
        if not unused:
            return []

        # MCP tools are the ones that actually cost the user a choice; built-ins
        # ride along regardless. Both still consume schema tokens, but we lead
        # with MCP because that's the actionable lever.
        mcp_unused = [t for t in unused if t.startswith("mcp__")]
        non_mcp_unused = [t for t in unused if not t.startswith("mcp__")]

        turns = max(1, len(session.assistant_turns))
        wasted_tokens = len(unused) * TOKENS_PER_TOOL_PER_TURN * turns
        dollars = pricing.dollars(input_tokens=wasted_tokens)

        if mcp_unused:
            servers = sorted({t.split("__")[1] for t in mcp_unused if "__" in t})
            head = (
                f"You loaded {len(defined)} tools "
                f"({len(mcp_unused)} from MCP servers: {', '.join(servers)}) "
                f"but only called {len(called)} this session. "
            )
        else:
            head = (
                f"You loaded {len(defined)} tools but only called "
                f"{len(called)} this session. "
            )

        recommendation = (
            head
            + f"Each unused schema costs ~{TOKENS_PER_TOOL_PER_TURN} tokens/turn × "
            + f"{turns} turns × {len(unused)} unused tools = ~{wasted_tokens:,} "
            + f"tokens (${dollars:0.2f}). Disable unused MCP servers for this project."
        )

        evidence = [f"unused: {', '.join(sorted(unused)[:8])}"]
        if len(unused) > 8:
            evidence[0] += f", … (+{len(unused) - 8} more)"
        if non_mcp_unused and not mcp_unused:
            evidence.append("none of the unused tools come from MCP servers")

        return [
            Finding(
                auditor=self.name,
                title=self.title,
                category=self.category,
                wasted_tokens=wasted_tokens,
                wasted_dollars=dollars,
                recommendation=recommendation,
                methodology=(
                    "Counted tools exposed to the session (from "
                    "deferred_tools_delta attachments) vs. tools actually "
                    f"invoked; charged unused schemas at ~{TOKENS_PER_TOOL_PER_TURN} "
                    "tokens/turn each."
                ),
                evidence=evidence,
            )
        ]
