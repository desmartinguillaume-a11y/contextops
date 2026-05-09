"""End-to-end smoke tests that invoke the real CLI as a subprocess.

These confirm the installed `contextops` entry point actually works the
way users will invoke it: from a shell, with no Python imports.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


CLI = [sys.executable, "-m", "contextops.cli"]


def _run(args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        CLI + args,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def test_version_command_prints_a_version() -> None:
    r = _run(["version"])
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip()  # non-empty


def test_help_lists_subcommands() -> None:
    r = _run(["--help"])
    assert r.returncode == 0
    out = r.stdout
    assert "analyze" in out
    assert "list" in out
    assert "version" in out


def test_analyze_with_no_sessions_exits_nonzero(tmp_path: Path) -> None:
    """Fresh-user case: $CLAUDE_HOME points at empty directory."""
    env = {"CLAUDE_HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    r = _run(["analyze"], env=env)
    assert r.returncode != 0
    assert "No Claude Code sessions" in (r.stdout + r.stderr)


def test_analyze_runs_against_synthetic_session(tmp_path: Path) -> None:
    """The realistic flow: pass an explicit JSONL path."""
    session = tmp_path / "session.jsonl"
    events = [
        {
            "type": "user",
            "message": {"role": "user", "content": "hi"},
        },
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "model": "claude-sonnet-4-6",
                "content": [{"type": "text", "text": "hello back"}],
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
        },
    ]
    session.write_text("\n".join(json.dumps(e) for e in events) + "\n")

    r = _run(["analyze", str(session)])
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "Context Utilization Report" in out
    assert "Total cost" in out


def test_list_handles_empty_home(tmp_path: Path) -> None:
    env = {"CLAUDE_HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    r = _run(["list"], env=env)
    assert r.returncode == 0
    assert "No Claude Code sessions" in r.stdout


def test_analyze_project_filter_matches_substring(tmp_path: Path) -> None:
    proj_dir = tmp_path / "projects" / "-home-me-myrepo"
    proj_dir.mkdir(parents=True)
    session = proj_dir / "abc.jsonl"
    session.write_text(json.dumps({
        "type": "assistant",
        "message": {
            "role": "assistant",
            "model": "claude-sonnet-4-6",
            "content": [{"type": "text", "text": "hi"}],
            "usage": {"input_tokens": 5, "output_tokens": 2},
        },
    }) + "\n")
    env = {"CLAUDE_HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    r = _run(["analyze", "--project", "myrepo"], env=env)
    assert r.returncode == 0, r.stderr
    assert "Context Utilization Report" in r.stdout


def test_analyze_project_filter_no_match_exits_nonzero(tmp_path: Path) -> None:
    (tmp_path / "projects").mkdir()
    env = {"CLAUDE_HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    r = _run(["analyze", "--project", "definitely-not-there"], env=env)
    assert r.returncode != 0
