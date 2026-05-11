"""Unit tests for DuplicateBashRuns auditor — covers F-02 scenarios S-02.1–S-02.9."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from contextops.auditors.duplicate_bash_runs import DuplicateBashRuns
from contextops.session import load_session


# ---------------------------------------------------------------------------
# S-02.1 — same command twice, no mutation → 1 finding
# ---------------------------------------------------------------------------

def test_s02_1_same_command_twice_no_mutation(builder, write_session):
    _, ids1 = builder.assistant(tool_uses=[("Bash", {"command": "git status"})])
    builder.tool_result(ids1[0], "On branch main")
    _, ids2 = builder.assistant(tool_uses=[("Bash", {"command": "git status"})])
    builder.tool_result(ids2[0], "On branch main")
    s = load_session(write_session(builder))
    findings = DuplicateBashRuns().run(s)
    assert len(findings) == 1
    f = findings[0]
    assert f.auditor == "duplicate_bash_runs"
    assert len(f.evidence) == 2
    assert "Cache" in f.fix_hint or "cache" in f.fix_hint


# ---------------------------------------------------------------------------
# S-02.2 — mutation in between → empty list
# ---------------------------------------------------------------------------

def test_s02_2_same_command_mutation_in_between(builder, write_session):
    _, ids1 = builder.assistant(tool_uses=[("Bash", {"command": "git status"})])
    builder.tool_result(ids1[0], "On branch main")
    _, ids2 = builder.assistant(tool_uses=[("Bash", {"command": "git commit -m 'fix'"})])
    builder.tool_result(ids2[0], "[main abc1234] fix")
    _, ids3 = builder.assistant(tool_uses=[("Bash", {"command": "git status"})])
    builder.tool_result(ids3[0], "nothing to commit")
    s = load_session(write_session(builder))
    findings = DuplicateBashRuns().run(s)
    assert findings == []


# ---------------------------------------------------------------------------
# S-02.3 — whitespace normalization: "git  status" == "git status" → 1 finding
# ---------------------------------------------------------------------------

def test_s02_3_whitespace_normalization(builder, write_session):
    _, ids1 = builder.assistant(tool_uses=[("Bash", {"command": "git  status"})])
    builder.tool_result(ids1[0], "On branch main")
    _, ids2 = builder.assistant(tool_uses=[("Bash", {"command": "git status"})])
    builder.tool_result(ids2[0], "On branch main")
    s = load_session(write_session(builder))
    findings = DuplicateBashRuns().run(s)
    assert len(findings) == 1
    # evidence should reference both calls
    assert len(findings[0].evidence) == 2


# ---------------------------------------------------------------------------
# S-02.4 — two distinct commands each repeated → 2 findings
# ---------------------------------------------------------------------------

def test_s02_4_two_distinct_commands_each_repeated(builder, write_session):
    _, ids1 = builder.assistant(tool_uses=[("Bash", {"command": "git status"})])
    builder.tool_result(ids1[0], "On branch main")
    _, ids2 = builder.assistant(tool_uses=[("Bash", {"command": "ls -la"})])
    builder.tool_result(ids2[0], "total 8")
    _, ids3 = builder.assistant(tool_uses=[("Bash", {"command": "git status"})])
    builder.tool_result(ids3[0], "On branch main")
    _, ids4 = builder.assistant(tool_uses=[("Bash", {"command": "ls -la"})])
    builder.tool_result(ids4[0], "total 8")
    s = load_session(write_session(builder))
    findings = DuplicateBashRuns().run(s)
    assert len(findings) == 2
    cmds = {f.evidence[0].split(": ")[1] for f in findings}
    assert any("git status" in c for c in cmds)
    assert any("ls -la" in c for c in cmds)


# ---------------------------------------------------------------------------
# S-02.5 — four repeats of same command → exactly 1 finding with 4 evidence entries
# ---------------------------------------------------------------------------

def test_s02_5_four_repeats_one_finding(builder, write_session):
    for _ in range(4):
        _, ids = builder.assistant(tool_uses=[("Bash", {"command": "cat pyproject.toml"})])
        builder.tool_result(ids[0], "[project]\nname = 'contextops'")
    s = load_session(write_session(builder))
    findings = DuplicateBashRuns().run(s)
    assert len(findings) == 1
    assert len(findings[0].evidence) == 4


# ---------------------------------------------------------------------------
# S-02.6 — no Bash calls (only Read/Glob) → empty list
# ---------------------------------------------------------------------------

def test_s02_6_no_bash_calls(builder, write_session):
    _, ids1 = builder.assistant(tool_uses=[("Read", {"file_path": "/x/a.py"})])
    builder.tool_result(ids1[0], "content")
    _, ids2 = builder.assistant(tool_uses=[("Glob", {"pattern": "**/*.py"})])
    builder.tool_result(ids2[0], "a.py\nb.py")
    s = load_session(write_session(builder))
    findings = DuplicateBashRuns().run(s)
    assert findings == []


# ---------------------------------------------------------------------------
# S-02.7 — all unique commands → empty list
# ---------------------------------------------------------------------------

def test_s02_7_all_unique_commands(builder, write_session):
    for cmd in ("git status", "ls -la", "pytest"):
        _, ids = builder.assistant(tool_uses=[("Bash", {"command": cmd})])
        builder.tool_result(ids[0], "output")
    s = load_session(write_session(builder))
    findings = DuplicateBashRuns().run(s)
    assert findings == []


# ---------------------------------------------------------------------------
# S-02.8 — malformed ToolUse (no "command" key) → no exception, skip gracefully
# ---------------------------------------------------------------------------

def test_s02_8_malformed_no_command_key(builder, write_session):
    # Bash ToolUse with empty input dict (no "command" key)
    _, ids1 = builder.assistant(tool_uses=[("Bash", {})])
    builder.tool_result(ids1[0], "")
    # Also add a normal one to make the session non-trivial
    _, ids2 = builder.assistant(tool_uses=[("Bash", {"command": "git status"})])
    builder.tool_result(ids2[0], "On branch main")
    s = load_session(write_session(builder))
    # Must not raise
    findings = DuplicateBashRuns().run(s)
    # The malformed call was skipped; only one normal call → no duplicate
    assert findings == []


# ---------------------------------------------------------------------------
# S-02.9 — zero turns → empty list
# ---------------------------------------------------------------------------

def test_s02_9_zero_turns(builder, write_session):
    # Empty builder — no events at all
    s = load_session(write_session(builder))
    findings = DuplicateBashRuns().run(s)
    assert findings == []
