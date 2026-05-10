"""Auto-fix: propose safe configuration patches from session evidence."""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from pathlib import Path

from .session import Session, discover_sessions, load_session, projects_dir


DEFAULT_MIN_SESSIONS = 5
DEFAULT_THRESHOLD = 0.8


@dataclass
class McpServerEvidence:
    server: str
    defined_in: int
    unused_in: int

    @property
    def unused_ratio(self) -> float:
        return self.unused_in / self.defined_in if self.defined_in else 0.0


@dataclass
class McpFix:
    project_slug: str
    sessions_inspected: list[Path]
    evidence: list[McpServerEvidence]
    servers_to_disable: list[str]
    skipped_reason: str | None = None

    @property
    def has_action(self) -> bool:
        return bool(self.servers_to_disable)


@dataclass
class SettingsPatch:
    """A unified-diff-able edit to a JSON settings file."""

    target: Path
    before: str
    after: str
    created: bool

    def unified_diff(self) -> str:
        rel = str(self.target)
        before_lines = self.before.splitlines() if self.before else []
        after_lines = self.after.splitlines()
        diff = difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{rel}" if not self.created else "/dev/null",
            tofile=f"b/{rel}",
            lineterm="",
        )
        return "\n".join(diff)


# ---------------------------------------------------------------------------
# MCP server detection
# ---------------------------------------------------------------------------

def _server_of(tool_name: str) -> str | None:
    if not tool_name.startswith("mcp__"):
        return None
    parts = tool_name.split("__", 2)
    if len(parts) < 2 or not parts[1]:
        return None
    return parts[1]


@dataclass
class _SessionView:
    path: Path
    defined_servers: set[str] = field(default_factory=set)
    called_servers: set[str] = field(default_factory=set)


def _view(session: Session, path: Path) -> _SessionView:
    v = _SessionView(path=path)
    for name in session.tool_definitions:
        srv = _server_of(name)
        if srv:
            v.defined_servers.add(srv)
    for tu in session.tool_calls():
        srv = _server_of(tu.name)
        if srv:
            v.called_servers.add(srv)
    return v


def sessions_for_project(project_slug: str) -> list[Path]:
    """Return all session JSONLs for a given project slug, newest first."""
    root = projects_dir() / project_slug
    if not root.exists():
        return []
    files = [p for p in root.glob("*.jsonl") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def compute_mcp_fix(
    project_slug: str,
    *,
    min_sessions: int = DEFAULT_MIN_SESSIONS,
    threshold: float = DEFAULT_THRESHOLD,
    max_sessions: int | None = None,
) -> McpFix:
    """Decide which MCP servers are safe to disable for `project_slug`.

    A server is flagged only if it has been *exposed* in at least
    `min_sessions` distinct sessions and was unused in `>= threshold`
    of them. Otherwise we stay silent: better miss a fix than break
    a workflow the user runs intermittently.
    """
    paths = sessions_for_project(project_slug)
    if max_sessions:
        paths = paths[:max_sessions]
    if len(paths) < min_sessions:
        return McpFix(
            project_slug=project_slug,
            sessions_inspected=paths,
            evidence=[],
            servers_to_disable=[],
            skipped_reason=(
                f"need at least {min_sessions} sessions for this project; "
                f"found {len(paths)}."
            ),
        )

    views: list[_SessionView] = []
    for p in paths:
        try:
            s = load_session(p)
        except Exception:
            continue
        views.append(_view(s, p))

    if len(views) < min_sessions:
        return McpFix(
            project_slug=project_slug,
            sessions_inspected=paths,
            evidence=[],
            servers_to_disable=[],
            skipped_reason=(
                f"only {len(views)} of {len(paths)} sessions could be loaded; "
                f"need {min_sessions}."
            ),
        )

    counts: dict[str, McpServerEvidence] = {}
    for v in views:
        for srv in v.defined_servers:
            ev = counts.setdefault(
                srv, McpServerEvidence(server=srv, defined_in=0, unused_in=0)
            )
            ev.defined_in += 1
            if srv not in v.called_servers:
                ev.unused_in += 1

    to_disable: list[str] = []
    for ev in counts.values():
        if ev.defined_in >= min_sessions and ev.unused_ratio >= threshold:
            to_disable.append(ev.server)

    return McpFix(
        project_slug=project_slug,
        sessions_inspected=[v.path for v in views],
        evidence=sorted(counts.values(), key=lambda e: e.server),
        servers_to_disable=sorted(to_disable),
    )


# ---------------------------------------------------------------------------
# Settings patch
# ---------------------------------------------------------------------------

SETTINGS_KEY = "disabledMcpjsonServers"


def build_settings_patch(project_cwd: Path, servers: list[str]) -> SettingsPatch:
    """Compute the patch to add `servers` to .claude/settings.local.json."""
    target = project_cwd / ".claude" / "settings.local.json"
    created = not target.exists()
    if created:
        before = ""
        data: dict = {}
    else:
        before = target.read_text(encoding="utf-8")
        try:
            data = json.loads(before) if before.strip() else {}
        except json.JSONDecodeError:
            data = {}
        if not isinstance(data, dict):
            data = {}

    existing = data.get(SETTINGS_KEY)
    existing_list = list(existing) if isinstance(existing, list) else []
    merged = sorted(set(existing_list) | set(servers))
    data[SETTINGS_KEY] = merged

    after = json.dumps(data, indent=4) + "\n"
    return SettingsPatch(target=target, before=before, after=after, created=created)


def apply_patch(patch: SettingsPatch) -> None:
    patch.target.parent.mkdir(parents=True, exist_ok=True)
    patch.target.write_text(patch.after, encoding="utf-8")


# ---------------------------------------------------------------------------
# Default project resolution
# ---------------------------------------------------------------------------

def latest_project_slug() -> str | None:
    """The project_slug of the most recent session, if any."""
    sessions = discover_sessions()
    if not sessions:
        return None
    return sessions[0].parent.name
