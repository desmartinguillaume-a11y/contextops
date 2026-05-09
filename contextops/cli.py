"""ContextOps CLI."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

import typer
from rich.console import Console

from . import __version__
from .auditors import all_auditors
from .pricing import Pricing
from .report import compute_bill, render_report, render_session_list
from .session import (
    discover_sessions,
    find_project,
    humanize_project_slug,
    latest_session,
    load_session,
)


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help='Your Claude Code session is a cloud bill. Audit it.',
)
console = Console()


def _resolve_session_path(
    session_path: Path | None,
    project: str | None,
) -> Path:
    if session_path:
        return session_path
    if project:
        p = find_project(project)
        if not p:
            console.print(f"[red]No session found for project matching '{project}'.[/red]")
            raise typer.Exit(code=2)
        return p
    p = latest_session()
    if not p:
        console.print(
            "[red]No Claude Code sessions found under ~/.claude/projects/.[/red]\n"
            "[dim]Set $CLAUDE_HOME or pass an explicit SESSION_PATH.[/dim]"
        )
        raise typer.Exit(code=2)
    return p


@app.command()
def analyze(
    session_path: Path | None = typer.Argument(
        None,
        exists=False,
        help="Path to a session JSONL. Defaults to the most recent session.",
    ),
    project: str | None = typer.Option(
        None, "--project", "-p", help="Latest session for a project (substring match)."
    ),
) -> None:
    """Audit a Claude Code session and print a FinOps-style report."""
    path = _resolve_session_path(session_path, project)
    session = load_session(path)

    console.print(f"[dim]Auditing[/dim] [cyan]{path}[/cyan]")
    findings = []
    for auditor in all_auditors():
        try:
            findings.extend(auditor.run(session))
        except Exception as exc:  # noqa: BLE001
            console.print(
                f"[red]auditor {auditor.name} crashed:[/red] {exc!r} "
                f"[dim](skipping)[/dim]"
            )

    findings.sort(key=lambda f: f.wasted_tokens, reverse=True)
    render_report(session, findings, console=console)


@app.command("list")
def list_sessions(
    limit: int = typer.Option(10, "--limit", "-n", help="How many sessions to show."),
) -> None:
    """List recent Claude Code sessions with their totals."""
    rows = []
    for path in discover_sessions()[:limit]:
        try:
            s = load_session(path)
        except Exception:
            continue
        usage = s.total_usage
        pricing = Pricing.for_model(s.model)
        cost = pricing.dollars(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_write_tokens=usage.cache_creation_input_tokens,
            cache_read_tokens=usage.cache_read_input_tokens,
        )
        ts = path.stat().st_mtime
        rows.append(
            {
                "when": _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M"),
                "project": humanize_project_slug(s.project_slug),
                "turns": len(s.assistant_turns),
                "tokens": usage.total,
                "cost": cost,
                "session_id": s.session_id,
            }
        )
    render_session_list(rows, console=console)


@app.command()
def version() -> None:
    """Print the installed ContextOps version."""
    console.print(__version__)


if __name__ == "__main__":  # pragma: no cover
    app()
