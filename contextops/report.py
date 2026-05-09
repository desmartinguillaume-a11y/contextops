"""Rich-based terminal renderer for ContextOps audit reports.

The visual target is an SRE / cloud-cost-explorer dashboard, not an AI
marketing page. No emojis, no exclamation marks, no encouragement copy.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from .auditors import Finding
from .pricing import Pricing
from .session import Session, humanize_project_slug


@dataclass
class Bill:
    total_tokens: int
    waste_tokens: int
    load_bearing_tokens: int
    total_dollars: float
    waste_dollars: float

    @property
    def waste_pct(self) -> float:
        if self.total_tokens <= 0:
            return 0.0
        return 100.0 * self.waste_tokens / self.total_tokens

    @property
    def load_bearing_pct(self) -> float:
        if self.total_tokens <= 0:
            return 0.0
        return 100.0 * self.load_bearing_tokens / self.total_tokens


def compute_bill(session: Session, findings: list[Finding]) -> Bill:
    usage = session.total_usage
    pricing = Pricing.for_model(session.model)
    total_dollars = pricing.dollars(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_write_tokens=usage.cache_creation_input_tokens,
        cache_read_tokens=usage.cache_read_input_tokens,
    )
    waste_tokens = sum(f.wasted_tokens for f in findings)
    waste_dollars = sum(f.wasted_dollars for f in findings)

    # Cap waste at the total billed; we'd rather undercount than print numbers
    # that can be ridiculed.
    waste_tokens = min(waste_tokens, usage.total)
    waste_dollars = min(waste_dollars, total_dollars)
    load_bearing = max(0, usage.total - waste_tokens)

    return Bill(
        total_tokens=usage.total,
        waste_tokens=waste_tokens,
        load_bearing_tokens=load_bearing,
        total_dollars=total_dollars,
        waste_dollars=waste_dollars,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_report(
    session: Session,
    findings: list[Finding],
    *,
    console: Console | None = None,
) -> None:
    console = console or Console()
    bill = compute_bill(session, findings)

    console.print()
    console.print(_header_panel(session, bill))
    console.print()
    console.print(_breakdown(findings, bill))
    console.print()
    console.print(_recommendations(findings))
    console.print()
    console.print(_footer(bill))
    console.print()


def _header_panel(session: Session, bill: Bill) -> Panel:
    project = humanize_project_slug(session.project_slug)
    subtitle = (
        f"[dim]{project}  ·  {session.model or 'unknown model'}  ·  "
        f"{len(session.assistant_turns)} turns[/dim]"
    )

    table = Table.grid(padding=(0, 2))
    table.add_column(justify="right", style="dim")
    table.add_column(justify="right")
    table.add_column()

    table.add_row("Total tokens billed", f"[bold]{bill.total_tokens:>10,}[/bold]", "")
    table.add_row(
        "Estimated load-bearing",
        f"{bill.load_bearing_tokens:>10,}",
        f"[green]({bill.load_bearing_pct:>4.1f}%)[/green]",
    )
    table.add_row(
        "Waste",
        f"{bill.waste_tokens:>10,}",
        f"[yellow]({bill.waste_pct:>4.1f}%)[/yellow]   →   [bold yellow]${bill.waste_dollars:.2f}[/bold yellow]",
    )
    table.add_row("Total cost", f"[bold]${bill.total_dollars:,.2f}[/bold]", "")

    body = Group(table, Text.from_markup(subtitle, justify="center"))
    return Panel(
        body,
        title="[bold]Context Utilization Report[/bold]",
        border_style="cyan",
        padding=(1, 2),
    )


def _breakdown(findings: list[Finding], bill: Bill) -> Panel:
    if not findings:
        return Panel(
            Text("No waste detected. Either you're a context-window virtuoso or the auditors missed something.", style="dim"),
            title="[bold]Top waste categories[/bold]",
            border_style="green",
            padding=(1, 2),
        )

    grouped: dict[str, list[Finding]] = {}
    for f in findings:
        grouped.setdefault(f.title, []).append(f)
    rows = sorted(
        ((title, sum(f.wasted_tokens for f in fs), sum(f.wasted_dollars for f in fs))
         for title, fs in grouped.items()),
        key=lambda r: r[1],
        reverse=True,
    )
    total_waste = bill.waste_tokens or 1

    table = Table.grid(padding=(0, 2))
    table.add_column(width=20)            # bar
    table.add_column(justify="right", width=7)  # pct
    table.add_column()                     # title

    bar_width = 20
    for title, tokens, _dollars in rows:
        share = tokens / total_waste
        filled = max(1, int(round(share * bar_width)))
        bar = "█" * filled + "░" * (bar_width - filled)
        pct = f"{share * 100:>5.1f}%"
        table.add_row(
            f"[yellow]{bar}[/yellow]",
            f"[bold]{pct}[/bold]",
            title,
        )

    return Panel(
        table,
        title="[bold]Top waste categories[/bold]",
        border_style="yellow",
        padding=(1, 2),
    )


def _recommendations(findings: list[Finding]) -> Panel:
    if not findings:
        return Panel(
            Text("Nothing to recommend.", style="dim"),
            title="[bold]Rightsizing recommendations[/bold]",
            border_style="dim",
            padding=(1, 2),
        )

    renderables: list = []
    for i, f in enumerate(findings):
        cost = f"[bold yellow]${f.wasted_dollars:.2f}[/bold yellow]"
        bullet = Text("→ ", style="cyan")
        line = Text.from_markup(f"{cost}  {f.recommendation}")
        renderables.append(Group(Text.assemble(bullet, line)))
        renderables.append(
            Text.from_markup(
                f"   [dim italic]how detected: {f.methodology}[/dim italic]"
            )
        )
        if f.evidence:
            renderables.append(
                Text.from_markup(
                    "   [dim]evidence: " + " · ".join(f.evidence) + "[/dim]"
                )
            )
        if i < len(findings) - 1:
            renderables.append(Text(""))

    return Panel(
        Group(*renderables),
        title="[bold]Rightsizing recommendations[/bold]",
        border_style="cyan",
        padding=(1, 2),
    )


def _footer(bill: Bill) -> Text:
    if bill.total_dollars <= 0:
        return Text("Estimated savings if all recommendations applied: $0.00 (0% of bill).", style="dim")
    pct = 100.0 * bill.waste_dollars / bill.total_dollars
    return Text.from_markup(
        f"[bold]Estimated savings if all recommendations applied:[/bold] "
        f"[bold yellow]${bill.waste_dollars:0.2f}[/bold yellow] "
        f"([bold yellow]{pct:0.0f}%[/bold yellow] of bill)."
    )


# ---------------------------------------------------------------------------
# Compact list view (for `contextops list`)
# ---------------------------------------------------------------------------

def render_session_list(rows: list[dict], console: Console | None = None) -> None:
    console = console or Console()
    if not rows:
        console.print("[dim]No Claude Code sessions found under ~/.claude/projects/.[/dim]")
        return

    table = Table(box=None, padding=(0, 2))
    table.add_column("when", style="dim")
    table.add_column("project")
    table.add_column("turns", justify="right")
    table.add_column("tokens", justify="right")
    table.add_column("cost", justify="right")
    table.add_column("session id", style="dim")

    for r in rows:
        table.add_row(
            r["when"],
            r["project"],
            str(r["turns"]),
            f"{r['tokens']:,}",
            f"${r['cost']:0.2f}",
            r["session_id"][:8],
        )

    console.print()
    console.print(Rule("[bold]Recent Claude Code sessions[/bold]", style="cyan"))
    console.print(table)
    console.print()
