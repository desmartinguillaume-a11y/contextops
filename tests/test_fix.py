"""Tests for the auto-fix module."""

from __future__ import annotations

import itertools
import json
import os
from pathlib import Path

import pytest

from contextops.fix import (
    apply_patch,
    build_settings_patch,
    compute_mcp_fix,
    sessions_for_project,
)


# ---------------------------------------------------------------------------
# Helpers: build small synthetic sessions on a fake CLAUDE_HOME
# ---------------------------------------------------------------------------

PROJECT_SLUG = "-home-me-myrepo"


@pytest.fixture
def claude_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    (home / "projects" / PROJECT_SLUG).mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_HOME", str(home))
    return home


_uuid = itertools.count(1)


def _u() -> str:
    return f"u_{next(_uuid):08d}"


def _make_session(
    home: Path,
    name: str,
    *,
    defined_mcp_servers: list[str],
    called_mcp_servers: list[str],
) -> Path:
    """Write a tiny JSONL with one assistant turn and the given tool topology."""
    events: list[dict] = []
    if defined_mcp_servers:
        events.append(
            {
                "type": "attachment",
                "uuid": _u(),
                "attachment": {
                    "type": "deferred_tools_delta",
                    "addedNames": [
                        f"mcp__{srv}__t1" for srv in defined_mcp_servers
                    ],
                },
            }
        )
    tool_uses = [
        {
            "type": "tool_use",
            "id": _u(),
            "name": f"mcp__{srv}__t1",
            "input": {},
        }
        for srv in called_mcp_servers
    ]
    events.append(
        {
            "type": "assistant",
            "uuid": _u(),
            "sessionId": name,
            "cwd": "/home/me/myrepo",
            "message": {
                "role": "assistant",
                "type": "message",
                "model": "claude-sonnet-4-6",
                "id": _u(),
                "content": ([{"type": "text", "text": "hi"}] + tool_uses),
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
        }
    )
    path = home / "projects" / PROJECT_SLUG / f"{name}.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    # Spread mtimes so ordering is deterministic.
    ts = path.stat().st_mtime + len(name)
    os.utime(path, (ts, ts))
    return path


# ---------------------------------------------------------------------------
# compute_mcp_fix
# ---------------------------------------------------------------------------

def test_skips_when_too_few_sessions(claude_home: Path) -> None:
    for i in range(2):
        _make_session(
            claude_home,
            f"s{i}",
            defined_mcp_servers=["github"],
            called_mcp_servers=[],
        )

    plan = compute_mcp_fix(PROJECT_SLUG, min_sessions=5)

    assert plan.skipped_reason is not None
    assert "5" in plan.skipped_reason
    assert plan.servers_to_disable == []


def test_flags_server_unused_across_all_sessions(claude_home: Path) -> None:
    for i in range(5):
        _make_session(
            claude_home,
            f"s{i}",
            defined_mcp_servers=["github", "linear"],
            called_mcp_servers=["linear"],
        )

    plan = compute_mcp_fix(PROJECT_SLUG, min_sessions=5, threshold=0.8)

    assert plan.skipped_reason is None
    assert plan.servers_to_disable == ["github"]
    by_server = {ev.server: ev for ev in plan.evidence}
    assert by_server["github"].unused_in == 5
    assert by_server["linear"].unused_in == 0


def test_keeps_intermittent_server(claude_home: Path) -> None:
    """github used in 2/5 sessions = 60% unused, below threshold 0.8 → keep."""
    for i in range(5):
        _make_session(
            claude_home,
            f"s{i}",
            defined_mcp_servers=["github"],
            called_mcp_servers=["github"] if i < 2 else [],
        )

    plan = compute_mcp_fix(PROJECT_SLUG, min_sessions=5, threshold=0.8)

    assert plan.servers_to_disable == []
    assert plan.evidence[0].unused_ratio == pytest.approx(0.6)


def test_threshold_lowered_flags_intermittent_server(claude_home: Path) -> None:
    for i in range(5):
        _make_session(
            claude_home,
            f"s{i}",
            defined_mcp_servers=["github"],
            called_mcp_servers=["github"] if i < 2 else [],
        )

    plan = compute_mcp_fix(PROJECT_SLUG, min_sessions=5, threshold=0.5)

    assert plan.servers_to_disable == ["github"]


def test_only_counts_sessions_where_server_was_defined(claude_home: Path) -> None:
    """A server defined in only 2/5 sessions doesn't qualify even if always unused."""
    for i in range(5):
        _make_session(
            claude_home,
            f"s{i}",
            defined_mcp_servers=["github"] if i < 2 else [],
            called_mcp_servers=[],
        )

    plan = compute_mcp_fix(PROJECT_SLUG, min_sessions=5, threshold=0.8)

    assert plan.servers_to_disable == []


def test_sessions_for_project_returns_newest_first(claude_home: Path) -> None:
    p1 = _make_session(claude_home, "old", defined_mcp_servers=[], called_mcp_servers=[])
    p2 = _make_session(claude_home, "new", defined_mcp_servers=[], called_mcp_servers=[])

    paths = sessions_for_project(PROJECT_SLUG)

    assert paths[0] == p2 and paths[-1] == p1


# ---------------------------------------------------------------------------
# build_settings_patch / apply_patch
# ---------------------------------------------------------------------------

def test_patch_creates_new_settings_file(tmp_path: Path) -> None:
    patch = build_settings_patch(tmp_path, ["github"])

    assert patch.created is True
    assert patch.before == ""
    assert "github" in patch.after
    assert "disabledMcpjsonServers" in patch.after
    diff = patch.unified_diff()
    assert "github" in diff
    assert "/dev/null" in diff


def test_patch_extends_existing_settings(tmp_path: Path) -> None:
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir()
    settings_file = settings_dir / "settings.local.json"
    settings_file.write_text(
        json.dumps(
            {"disabledMcpjsonServers": ["sentry"], "permissions": {"allow": ["Bash"]}},
            indent=4,
        )
        + "\n"
    )

    patch = build_settings_patch(tmp_path, ["github"])

    assert patch.created is False
    after = json.loads(patch.after)
    assert sorted(after["disabledMcpjsonServers"]) == ["github", "sentry"]
    assert after["permissions"] == {"allow": ["Bash"]}


def test_patch_dedupes_already_disabled(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.local.json").write_text(
        json.dumps({"disabledMcpjsonServers": ["github"]}, indent=4) + "\n"
    )

    patch = build_settings_patch(tmp_path, ["github"])

    after = json.loads(patch.after)
    assert after["disabledMcpjsonServers"] == ["github"]


def test_apply_patch_writes_file(tmp_path: Path) -> None:
    patch = build_settings_patch(tmp_path, ["github"])

    apply_patch(patch)

    assert patch.target.exists()
    written = json.loads(patch.target.read_text())
    assert written["disabledMcpjsonServers"] == ["github"]
