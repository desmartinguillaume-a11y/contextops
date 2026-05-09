"""ContextOps CLI."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

import typer
from rich.console import Console

from . import __version__
from .auditors import all_auditors
from .fix import (
    DEFAULT_MIN_SESSIONS,
    DEFAULT_THRESHOLD,
    apply_patch,
    build_settings_patch,
    compute_mcp_fix,
    latest_project_slug,
)
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
def fix(
    project: str | None = typer.Option(
        None,
        "--project",
        "-p",
        help="Project slug or substring. Defaults to the most recent project.",
    ),
    cwd: Path | None = typer.Option(
        None,
        "--cwd",
        help="Project directory to patch. Defaults to the cwd recorded in the session.",
    ),
    min_sessions: int = typer.Option(
        DEFAULT_MIN_SESSIONS,
        "--min-sessions",
        help="Refuse to recommend disabling a server unless it appeared in ≥N sessions.",
    ),
    threshold: float = typer.Option(
        DEFAULT_THRESHOLD,
        "--threshold",
        help="Fraction of those sessions where the server must be unused (0.0–1.0).",
    ),
    apply: bool = typer.Option(
        False,
        "--apply/--no-apply",
        help="Write the patch to disk. Default: print the diff only.",
    ),
) -> None:
    """Propose safe configuration patches based on multi-session evidence.

    Currently disables MCP servers that are exposed but never invoked across
    the last N sessions of a project. By default prints a unified diff;
    pass --apply to write .claude/settings.local.json.
    """
    if project:
        match = find_project(project)
        if not match:
            console.print(f"[red]No project found matching '{project}'.[/red]")
            raise typer.Exit(code=2)
        project_slug = match.parent.name
        recorded_cwd = load_session(match).cwd
    else:
        project_slug = latest_project_slug()
        if not project_slug:
            console.print(
                "[red]No Claude Code sessions found under ~/.claude/projects/.[/red]"
            )
            raise typer.Exit(code=2)
        latest = latest_session()
        recorded_cwd = load_session(latest).cwd if latest else None

    plan = compute_mcp_fix(
        project_slug, min_sessions=min_sessions, threshold=threshold
    )

    console.print(
        f"[dim]Project:[/dim] [cyan]{humanize_project_slug(project_slug)}[/cyan]  "
        f"[dim]Sessions inspected:[/dim] {len(plan.sessions_inspected)}"
    )

    if plan.skipped_reason:
        console.print(f"[yellow]Skipped:[/yellow] {plan.skipped_reason}")
        console.print(
            "[dim]Run more sessions in this project, or lower --min-sessions "
            "if you understand the risk.[/dim]"
        )
        return

    if plan.evidence:
        rows = []
        for ev in plan.evidence:
            mark = "→" if ev.server in plan.servers_to_disable else " "
            rows.append(
                f"  {mark} {ev.server:<24} unused in "
                f"{ev.unused_in}/{ev.defined_in} sessions "
                f"({ev.unused_ratio:.0%})"
            )
        console.print("\n".join(rows))

    if not plan.has_action:
        console.print("[green]Nothing to fix — no MCP server qualifies.[/green]")
        return

    target_cwd = cwd or (Path(recorded_cwd) if recorded_cwd else None)
    if target_cwd is None:
        console.print(
            "[yellow]Could not determine project cwd from session; "
            "pass --cwd PATH to write a patch.[/yellow]"
        )
        return

    patch = build_settings_patch(target_cwd, plan.servers_to_disable)
    diff = patch.unified_diff()
    console.print(
        f"\n[dim]Proposed patch for[/dim] [cyan]{patch.target}[/cyan]"
        + ("  [dim](new file)[/dim]" if patch.created else "")
    )
    console.print(diff or "[dim](no diff — already disabled)[/dim]")

    if apply:
        if not diff:
            console.print("[dim]Nothing to write.[/dim]")
            return
        apply_patch(patch)
        console.print(f"[green]✓[/green] wrote {patch.target}")
    else:
        console.print(
            "\n[dim]Run again with --apply to write the patch.[/dim]"
        )


@app.command()
def version() -> None:
    """Print the installed ContextOps version."""
    console.print(__version__)


if __name__ == "__main__":  # pragma: no cover
    app()
