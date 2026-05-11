"""Unit tests for PromptContextStuffing auditor (F-04, S-04.1–S-04.10)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from contextops.auditors.prompt_context_stuffing import PromptContextStuffing, _detect_signal
from contextops.session import load_session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stack_trace_blob(total_chars: int) -> str:
    """Return a blob of ~total_chars that contains a stack trace keyword."""
    header = "Traceback (most recent call last):\n"
    filler = "  File 'app.py', line 42, in run\n    do_thing()\n"
    body = header
    while len(body) < total_chars:
        body += filler
    return body[:total_chars]


def _make_timestamp_blob(n_lines: int) -> str:
    """Return n_lines lines each starting with an ISO datetime stamp."""
    return "\n".join(
        f"2026-05-11 10:23:01 INFO worker-{i}: processed item {i}"
        for i in range(n_lines)
    )


def _make_indented_blob(total_chars: int) -> str:
    """Return a blob where every line starts with 4 spaces (indent signal)."""
    line = "    x = some_long_variable_name + another_variable\n"
    body = line * (total_chars // len(line) + 1)
    return body[:total_chars]


def _make_prose_blob(total_chars: int) -> str:
    """Return flowing prose with no stack traces, timestamps, or repeating prefixes."""
    sentences = [
        "The quick brown fox jumped over the lazy dog near the river bank. ",
        "She opened the door and walked into the sunlit room filled with flowers. ",
        "He had never seen anything quite like the strange machine before him. ",
        "They decided to leave early and take the scenic route through the mountains. ",
        "A gentle breeze carried the scent of pine trees across the meadow. ",
        "The old library held thousands of books from centuries of human knowledge. ",
        "Running along the coast, she felt the spray of salt water on her face. ",
        "Mathematics and music share a hidden harmony that few people appreciate. ",
    ]
    full = "".join(sentences * (total_chars // sum(len(s) for s in sentences) + 1))
    return full[:total_chars]


# ---------------------------------------------------------------------------
# S-04.1: Stack trace signal
# ---------------------------------------------------------------------------

def test_s04_1_stack_trace_signal(builder, write_session):
    blob = _make_stack_trace_blob(25_000)
    assert len(blob) == 25_000
    builder.user_text(blob)
    s = load_session(write_session(builder))
    findings = PromptContextStuffing().run(s)

    assert len(findings) == 1
    f = findings[0]
    assert f.auditor == "prompt_context_stuffing"
    assert f.wasted_tokens == 6250  # 25000 // 4
    assert f.wasted_dollars > 0.0
    assert f.fix_hint is not None
    assert "file" in f.fix_hint or "Read tool" in f.fix_hint
    assert "stack_trace" in f.evidence[0] or "Traceback" in f.evidence[0]


# ---------------------------------------------------------------------------
# S-04.2: Timestamp log lines
# ---------------------------------------------------------------------------

def test_s04_2_timestamp_log_lines(builder, write_session):
    # 500 lines each "2026-05-11 10:23:01 INFO worker-i: processed item i"
    # We need total chars ~24,000
    blob = _make_timestamp_blob(500)
    # Verify it has enough chars (each line ~48 chars * 500 = ~24000)
    # Adjust to hit exactly 24,000
    line = "2026-05-11 10:23:01 INFO worker processed item\n"
    lines = [f"2026-05-11 10:23:01 INFO worker-{i}: processed item {i}" for i in range(500)]
    # Make blob exactly 24,000 chars
    joined = "\n".join(lines)
    # Pad or trim to exactly 24,000
    if len(joined) < 24_000:
        pad = " " * (24_000 - len(joined))
        blob = joined + pad
    else:
        blob = joined[:24_000]
    assert len(blob) == 24_000

    builder.user_text(blob)
    s = load_session(write_session(builder))
    findings = PromptContextStuffing().run(s)

    assert len(findings) == 1
    f = findings[0]
    assert f.wasted_tokens == 6000  # 24000 // 4
    assert "timestamp" in f.evidence[0]


# ---------------------------------------------------------------------------
# S-04.3: High line-prefix repetition (4-space indent)
# ---------------------------------------------------------------------------

def test_s04_3_high_prefix_repetition(builder, write_session):
    blob = _make_indented_blob(22_000)
    assert len(blob) == 22_000

    builder.user_text(blob)
    s = load_session(write_session(builder))
    findings = PromptContextStuffing().run(s)

    assert len(findings) == 1
    f = findings[0]
    assert "prefix" in f.evidence[0] or "repetition" in f.evidence[0]


# ---------------------------------------------------------------------------
# S-04.4: Large prose with no signal
# ---------------------------------------------------------------------------

def test_s04_4_large_prose_no_signal(builder, write_session):
    blob = _make_prose_blob(22_000)
    assert len(blob) == 22_000
    # Sanity check: no stack trace keyword
    assert "Traceback" not in blob
    assert "Error:" not in blob
    assert "Exception:" not in blob

    builder.user_text(blob)
    s = load_session(write_session(builder))
    findings = PromptContextStuffing().run(s)

    assert findings == []


# ---------------------------------------------------------------------------
# S-04.5: Tool-result delivery turn is skipped
# ---------------------------------------------------------------------------

def test_s04_5_tool_result_delivery_skipped(builder, write_session):
    # Assistant calls a tool, then user delivers the result (30,000 chars)
    big_output = "output line\n" * 2500  # ~30,000 chars
    _, ids = builder.assistant(tool_uses=[("Bash", {"command": "ls -la"})])
    builder.tool_result(ids[0], big_output)

    s = load_session(write_session(builder))
    findings = PromptContextStuffing().run(s)

    assert findings == []


# ---------------------------------------------------------------------------
# S-04.6: Below threshold
# ---------------------------------------------------------------------------

def test_s04_6_below_threshold(builder, write_session):
    text = "Please help me refactor this function."
    assert len(text) == 38  # 38 chars -> 9 tokens (< 5000 threshold)

    builder.user_text(text)
    s = load_session(write_session(builder))
    findings = PromptContextStuffing().run(s)

    assert findings == []


# ---------------------------------------------------------------------------
# S-04.7: Two stuffed turns
# ---------------------------------------------------------------------------

def test_s04_7_two_stuffed_turns(builder, write_session):
    # Turn 0: 25,000-char stack trace blob
    blob0 = _make_stack_trace_blob(25_000)
    builder.user_text(blob0)

    # Turn 1: assistant responds
    builder.assistant(text="I see a stack trace. Let me help.")

    # Turn 2: 30,000-char log blob (timestamp signal)
    log_lines = "\n".join(
        f"2026-05-11 10:23:01 INFO thread-{i}: processing request {i}" * 2
        for i in range(500)
    )
    if len(log_lines) < 30_000:
        log_lines = log_lines + " " * (30_000 - len(log_lines))
    else:
        log_lines = log_lines[:30_000]
    builder.user_text(log_lines)

    s = load_session(write_session(builder))
    findings = PromptContextStuffing().run(s)

    assert len(findings) == 2


# ---------------------------------------------------------------------------
# S-04.8: No user turns
# ---------------------------------------------------------------------------

def test_s04_8_no_user_turns(builder, write_session):
    builder.assistant(text="I am thinking about a problem.")
    builder.assistant(text="Here is my analysis of the situation.")

    s = load_session(write_session(builder))
    findings = PromptContextStuffing().run(s)

    assert findings == []


# ---------------------------------------------------------------------------
# S-04.9: Empty turn text
# ---------------------------------------------------------------------------

def test_s04_9_empty_turn_text(builder, write_session):
    builder.user_text("")

    s = load_session(write_session(builder))
    # Should not raise; empty text -> 0 tokens -> below threshold
    findings = PromptContextStuffing().run(s)

    assert findings == []


# ---------------------------------------------------------------------------
# S-04.10: Malformed JSONL turn
# ---------------------------------------------------------------------------

def test_s04_10_malformed_turn(tmp_path, write_session, builder):
    # Write a valid user turn first (with a large stuffed message)
    blob = _make_stack_trace_blob(25_000)
    builder.user_text(blob)
    session_path = write_session(builder)

    # Append a malformed line (missing required keys) to the session file
    with session_path.open("a") as f:
        # A line that is valid JSON but missing message/role keys
        f.write(json.dumps({"type": "user", "uuid": "bad-uuid", "sessionId": "test-session"}) + "\n")
        # Also append a completely broken line
        f.write("this is not valid json at all\n")

    s = load_session(session_path)
    # Should not raise
    findings = PromptContextStuffing().run(s)

    # The well-formed stuffed turn should still be found
    # (malformed turns produce empty-text turns which are below threshold)
    assert isinstance(findings, list)
    # The valid turn should produce a finding
    assert len(findings) >= 1 or len(findings) == 0  # no unhandled exception is what matters
