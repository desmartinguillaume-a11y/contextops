"""Unit tests for OversizedToolOutputs auditor — F-01 scenarios S-01.1 through S-01.8."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from contextops.auditors.oversized_tool_outputs import OversizedToolOutputs
from contextops.session import load_session


# ---------------------------------------------------------------------------
# S-01.1: Bash result exceeds 2,000-token threshold
# ---------------------------------------------------------------------------

def test_s01_1_bash_exceeds_threshold(builder, write_session):
    """9,000-char Bash result → 1 finding, wasted_tokens==2250, fix_hint mentions Truncate."""
    content = "x" * 9000  # estimate_tokens("x"*9000) == 9000//4 == 2250
    _, ids = builder.assistant(tool_uses=[("Bash", {"command": "ls -la"})])
    builder.tool_result(ids[0], content)
    path = write_session(builder)
    session = load_session(path)

    findings = OversizedToolOutputs().run(session)

    assert len(findings) == 1
    f = findings[0]
    assert f.wasted_tokens == 2250
    assert f.auditor == "oversized_tool_outputs"
    assert "Truncate" in f.fix_hint or "truncate" in f.fix_hint
    assert "Bash" in f.evidence[0]
    assert "2,250" in f.evidence[0]


# ---------------------------------------------------------------------------
# S-01.2: Read tool result exceeds 5,000-token threshold
# ---------------------------------------------------------------------------

def test_s01_2_file_read_exceeds_threshold(builder, write_session):
    """21,000-char Read result → 1 finding, wasted_tokens==5250, fix_hint mentions offset or section."""
    content = "y" * 21000  # estimate_tokens("y"*21000) == 21000//4 == 5250
    _, ids = builder.assistant(tool_uses=[("Read", {"file_path": "/x/big_file.py"})])
    builder.tool_result(ids[0], content)
    path = write_session(builder)
    session = load_session(path)

    findings = OversizedToolOutputs().run(session)

    assert len(findings) == 1
    f = findings[0]
    assert f.wasted_tokens == 5250
    assert "offset" in f.fix_hint or "section" in f.fix_hint
    assert "Read" in f.evidence[0]
    assert "5,250" in f.evidence[0]


# ---------------------------------------------------------------------------
# S-01.3: Both Bash and Read are oversized → 2 findings
# ---------------------------------------------------------------------------

def test_s01_3_both_oversized(builder, write_session):
    """9,000-char Bash + 21,000-char Read → 2 findings with wasted_tokens 2250 and 5250."""
    bash_content = "x" * 9000   # 2250 tokens
    read_content = "y" * 21000  # 5250 tokens

    _, bash_ids = builder.assistant(tool_uses=[("Bash", {"command": "find . -type f"})])
    builder.tool_result(bash_ids[0], bash_content)
    _, read_ids = builder.assistant(tool_uses=[("Read", {"file_path": "/x/big_file.py"})])
    builder.tool_result(read_ids[0], read_content)
    path = write_session(builder)
    session = load_session(path)

    findings = OversizedToolOutputs().run(session)

    assert len(findings) == 2
    token_counts = {f.wasted_tokens for f in findings}
    assert 2250 in token_counts
    assert 5250 in token_counts


# ---------------------------------------------------------------------------
# S-01.4: Bash result below threshold → empty list
# ---------------------------------------------------------------------------

def test_s01_4_below_threshold(builder, write_session):
    """6-char Bash result (1 token) → empty list."""
    content = "exit 0\n"  # 7 chars → estimate_tokens == max(1, 7//4) == 1
    _, ids = builder.assistant(tool_uses=[("Bash", {"command": "exit 0"})])
    builder.tool_result(ids[0], content)
    path = write_session(builder)
    session = load_session(path)

    findings = OversizedToolOutputs().run(session)

    assert findings == []


# ---------------------------------------------------------------------------
# S-01.5: ToolUse with no matching ToolResult → empty list, no exception
# ---------------------------------------------------------------------------

def test_s01_5_missing_tool_result(builder, write_session):
    """ToolUse with id 'tu_abc' and no ToolResult → empty list, no exception."""
    # Add a Bash tool_use but do NOT add a tool_result
    _, _ids = builder.assistant(tool_uses=[("Bash", {"command": "echo hello"})])
    # deliberately omit: builder.tool_result(...)
    path = write_session(builder)
    session = load_session(path)

    findings = OversizedToolOutputs().run(session)

    assert findings == []


# ---------------------------------------------------------------------------
# S-01.6: ToolResult with null/empty content → empty list, no exception
# ---------------------------------------------------------------------------

def test_s01_6_null_content(builder, write_session, tmp_path):
    """ToolResult with content=null → empty list, no exception."""
    # Build a JSONL with a tool_result that has null content
    _, ids = builder.assistant(tool_uses=[("Bash", {"command": "echo hi"})])
    # Write manually so we can set content to null
    import itertools
    events = list(builder.events)
    # Add a user turn with tool_result content = null
    events.append({
        "type": "user",
        "uuid": "uuid_null",
        "sessionId": "test-session",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": ids[0],
                    "is_error": False,
                    "content": None,
                }
            ],
        },
    })
    jsonl_path = tmp_path / "null_content.jsonl"
    jsonl_path.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    session = load_session(jsonl_path)

    findings = OversizedToolOutputs().run(session)

    assert findings == []


# ---------------------------------------------------------------------------
# S-01.7: Session with no ToolUse events → empty list
# ---------------------------------------------------------------------------

def test_s01_7_no_tool_calls(builder, write_session):
    """Session with only text turns → empty list."""
    builder.user_text("Hello Claude")
    builder.assistant(text="Hi there!")
    path = write_session(builder)
    session = load_session(path)

    findings = OversizedToolOutputs().run(session)

    assert findings == []


# ---------------------------------------------------------------------------
# S-01.8: Malformed ToolUse (missing "input" key) → no unhandled exception
# ---------------------------------------------------------------------------

def test_s01_8_malformed_input_key(builder, write_session, tmp_path):
    """Malformed tool_use (no 'input' key) → load_session handles gracefully, no exception."""
    # Write a JSONL with a tool_use block that omits the 'input' key
    malformed_event = {
        "type": "assistant",
        "uuid": "uuid_bad",
        "sessionId": "test-session",
        "message": {
            "role": "assistant",
            "type": "message",
            "model": "claude-sonnet-4-6",
            "id": "msg_bad",
            "content": [
                {
                    "type": "tool_use",
                    "id": "tu_malformed",
                    "name": "Bash",
                    # 'input' key intentionally omitted
                }
            ],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        },
    }
    jsonl_path = tmp_path / "malformed.jsonl"
    jsonl_path.write_text(json.dumps(malformed_event) + "\n")
    session = load_session(jsonl_path)

    # Should not raise — returns [] or findings for well-formed events only
    findings = OversizedToolOutputs().run(session)

    assert isinstance(findings, list)
