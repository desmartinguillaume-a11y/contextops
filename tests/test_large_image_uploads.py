"""Unit tests for LargeImageUploads auditor — covers all 9 F-03 scenarios."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from contextops.auditors.large_image_uploads import IMAGE_THRESHOLD, LargeImageUploads
from contextops.session import load_session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _image_block(data: str, media_type: str = "image/png") -> dict:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": data,
        },
    }


def _user_turn(content, session_id: str = "test-session") -> dict:
    """Build a minimal user-type JSONL event dict."""
    return {
        "type": "user",
        "sessionId": session_id,
        "message": {
            "role": "user",
            "content": content,
        },
    }


def _assistant_turn(content, session_id: str = "test-session") -> dict:
    """Build a minimal assistant-type JSONL event dict."""
    return {
        "type": "assistant",
        "sessionId": session_id,
        "message": {
            "role": "assistant",
            "model": "claude-sonnet-4-6",
            "content": content,
            "usage": {"input_tokens": 100, "output_tokens": 50},
        },
    }


def write_image_session(tmp_path: Path, turns_data: list[dict]) -> Path:
    """Write a minimal JSONL session file with raw turn dicts."""
    session_dir = tmp_path / "projects" / "test-project"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_file = session_dir / "session.jsonl"
    with session_file.open("w") as f:
        for turn_dict in turns_data:
            f.write(json.dumps(turn_dict) + "\n")
    return session_file


# ---------------------------------------------------------------------------
# S-03.1: Single large image
# ---------------------------------------------------------------------------

def test_s03_1_single_large_image(tmp_path):
    """Turn 2 (3rd user turn, 0-based index 2) with 60,000-char base64 → 1 finding."""
    big_data = "A" * 60_000
    turns = [
        _user_turn("hello"),           # user index 0
        _user_turn("second message"),  # user index 1
        _user_turn([_image_block(big_data)]),  # user index 2
    ]
    session_file = write_image_session(tmp_path, turns)
    session = load_session(session_file)

    findings = LargeImageUploads().run(session)

    assert len(findings) == 1
    f = findings[0]
    assert f.auditor == "large_image_uploads"
    assert f.wasted_tokens == 15_000  # 60000 // 4
    assert f.wasted_dollars > 0.0
    assert f.fix_hint is not None
    assert "Resize" in f.fix_hint or "Files API" in f.fix_hint
    assert len(f.evidence) > 0
    assert "turn 2" in f.evidence[0]


# ---------------------------------------------------------------------------
# S-03.2: Same large image in two turns
# ---------------------------------------------------------------------------

def test_s03_2_same_large_image_two_turns(tmp_path):
    """Turns 0 and 2 with same 55,000-char base64 → ≥2 findings."""
    same_data = "B" * 55_000
    turns = [
        _user_turn([_image_block(same_data)]),   # user index 0
        _user_turn("some text"),                  # user index 1
        _user_turn([_image_block(same_data)]),   # user index 2
    ]
    session_file = write_image_session(tmp_path, turns)
    session = load_session(session_file)

    findings = LargeImageUploads().run(session)

    # Expect: 2 oversized findings (one per occurrence) + 1 duplicate finding = 3
    assert len(findings) >= 2

    # Verify at least one finding is oversized (wasted_tokens >= 13750)
    oversized = [f for f in findings if f.wasted_tokens >= 13_750 and f.fix_hint and "Resize" in f.fix_hint]
    assert len(oversized) >= 1, "Expected at least one oversized finding"

    # Verify duplicate finding references the count "2"
    dup_findings = [f for f in findings if f.fix_hint and "2" in f.fix_hint]
    assert len(dup_findings) >= 1, "Expected a duplicate finding mentioning '2'"


# ---------------------------------------------------------------------------
# S-03.3: Image below threshold
# ---------------------------------------------------------------------------

def test_s03_3_image_below_threshold(tmp_path):
    """Turn with 300-char base64 → empty list."""
    small_data = "C" * 300
    turns = [_user_turn([_image_block(small_data)])]
    session_file = write_image_session(tmp_path, turns)
    session = load_session(session_file)

    findings = LargeImageUploads().run(session)

    assert findings == []


# ---------------------------------------------------------------------------
# S-03.4: URL source type skipped
# ---------------------------------------------------------------------------

def test_s03_4_url_source_type_skipped(tmp_path):
    """image block with source.type=='url' (no 'data' field) → empty list, no exception."""
    url_block = {
        "type": "image",
        "source": {
            "type": "url",
            "url": "https://example.com/image.png",
        },
    }
    turns = [_user_turn([url_block])]
    session_file = write_image_session(tmp_path, turns)
    session = load_session(session_file)

    findings = LargeImageUploads().run(session)

    assert findings == []


# ---------------------------------------------------------------------------
# S-03.5: Content is string not list
# ---------------------------------------------------------------------------

def test_s03_5_content_is_string_not_list(tmp_path):
    """Turn where message.content is a plain string → empty list, no exception."""
    turns = [_user_turn("Hello world")]
    session_file = write_image_session(tmp_path, turns)
    session = load_session(session_file)

    findings = LargeImageUploads().run(session)

    assert findings == []


# ---------------------------------------------------------------------------
# S-03.6: Image block missing source key
# ---------------------------------------------------------------------------

def test_s03_6_image_block_missing_source_key(tmp_path):
    """content block with type=='image' but no 'source' key → empty list, no exception."""
    block_no_source = {"type": "image"}
    turns = [_user_turn([block_no_source])]
    session_file = write_image_session(tmp_path, turns)
    session = load_session(session_file)

    findings = LargeImageUploads().run(session)

    assert findings == []


# ---------------------------------------------------------------------------
# S-03.7: No image blocks
# ---------------------------------------------------------------------------

def test_s03_7_no_image_blocks(tmp_path):
    """Session with only text blocks → empty list."""
    text_block = {"type": "text", "text": "Just some text content here."}
    turns = [
        _user_turn([text_block]),
        _assistant_turn([{"type": "text", "text": "Response here."}]),
    ]
    session_file = write_image_session(tmp_path, turns)
    session = load_session(session_file)

    findings = LargeImageUploads().run(session)

    assert findings == []


# ---------------------------------------------------------------------------
# S-03.8: Multiple different large images same turn
# ---------------------------------------------------------------------------

def test_s03_8_multiple_different_large_images_same_turn(tmp_path):
    """Turn with two distinct 60,000-char image blocks → exactly 2 findings."""
    data_a = "D" * 60_000
    data_b = "E" * 60_000  # different content → different hash
    turns = [
        _user_turn([_image_block(data_a), _image_block(data_b)]),
    ]
    session_file = write_image_session(tmp_path, turns)
    session = load_session(session_file)

    findings = LargeImageUploads().run(session)

    # Both are oversized; they are distinct so no duplicate finding
    assert len(findings) == 2
    for f in findings:
        assert f.auditor == "large_image_uploads"
        assert f.wasted_tokens == 15_000


# ---------------------------------------------------------------------------
# S-03.9: data field is integer
# ---------------------------------------------------------------------------

def test_s03_9_data_field_is_integer(tmp_path):
    """image block where source.data is 42 (integer not string) → empty list, no exception."""
    bad_block = {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": 42,  # integer, not string
        },
    }
    turns = [_user_turn([bad_block])]
    session_file = write_image_session(tmp_path, turns)
    session = load_session(session_file)

    # Must not raise
    findings = LargeImageUploads().run(session)

    assert findings == []
