"""Loader fuzz / robustness tests.

We don't trust the on-disk format. Real-world Claude Code session files
can be truncated mid-write, mix unknown event types, contain malformed
JSON, or use field shapes we haven't seen yet. The loader must never
crash; it should silently skip what it can't parse.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from contextops.session import Usage, load_session


def _write(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_handles_empty_file(tmp_path: Path) -> None:
    p = _write(tmp_path / "empty.jsonl", [])
    s = load_session(p)
    assert s.turns == []
    assert s.total_usage.total == 0


def test_skips_blank_lines(tmp_path: Path) -> None:
    p = _write(tmp_path / "blanks.jsonl", ["", "   ", "", ""])
    s = load_session(p)
    assert s.turns == []


def test_skips_malformed_json_lines(tmp_path: Path) -> None:
    good = json.dumps(
        {"type": "user", "message": {"role": "user", "content": "hi"}}
    )
    p = _write(
        tmp_path / "mixed.jsonl",
        [
            "this is not json",
            "{ also not json,,,",
            good,
            "{",  # truncated mid-write
        ],
    )
    s = load_session(p)
    assert len(s.user_turns) == 1


def test_unknown_event_types_are_ignored(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "unknown.jsonl",
        [
            json.dumps({"type": "queue-operation", "operation": "enqueue"}),
            json.dumps({"type": "skill_listing"}),
            json.dumps({"type": "todo_reminder", "items": []}),
            json.dumps({"type": "system", "subtype": "stop_hook_summary"}),
            json.dumps({"type": "ai-title", "aiTitle": "x"}),
            json.dumps({"type": "last-prompt", "lastPrompt": "x"}),
            json.dumps({"type": "user", "message": {"role": "user", "content": "x"}}),
        ],
    )
    s = load_session(p)
    assert len(s.user_turns) == 1


def test_assistant_without_usage_does_not_crash(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "no_usage.jsonl",
        [
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "model": "claude-sonnet-4-6",
                        "content": [{"type": "text", "text": "hi"}],
                        # no `usage` field at all
                    },
                }
            )
        ],
    )
    s = load_session(p)
    assert len(s.assistant_turns) == 1
    assert s.assistant_turns[0].usage == Usage()


def test_user_content_as_list_with_unknown_blocks(tmp_path: Path) -> None:
    """User content blocks may include shapes we don't recognize; ignore safely."""
    p = _write(
        tmp_path / "unknown_blocks.jsonl",
        [
            json.dumps(
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {"data": "..."}},
                            {"type": "text", "text": "hello"},
                            {"type": "tool_result", "tool_use_id": "tu_1", "content": "ok"},
                            {"type": "weird_future_block", "payload": 42},
                        ],
                    },
                }
            )
        ],
    )
    s = load_session(p)
    assert len(s.user_turns) == 1
    assert s.user_turns[0].tool_results[0].tool_use_id == "tu_1"
    assert "hello" in s.user_turns[0].text


def test_tool_result_content_as_list_of_text_blocks(tmp_path: Path) -> None:
    """tool_result.content can be a list of text blocks (multimodal API shape)."""
    p = _write(
        tmp_path / "multimodal.jsonl",
        [
            json.dumps(
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "tu_1",
                                "content": [
                                    {"type": "text", "text": "first piece"},
                                    {"type": "text", "text": "second piece"},
                                ],
                            }
                        ],
                    },
                }
            )
        ],
    )
    s = load_session(p)
    res = s.user_turns[0].tool_results[0]
    assert "first piece" in res.content
    assert "second piece" in res.content


def test_assistant_text_content_as_string(tmp_path: Path) -> None:
    """Older / simpler shapes may set content to a plain string instead of list."""
    p = _write(
        tmp_path / "plain_text.jsonl",
        [
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "model": "claude-sonnet-4-6",
                        "content": "Just a plain string response.",
                        "usage": {"input_tokens": 1, "output_tokens": 1},
                    },
                }
            )
        ],
    )
    s = load_session(p)
    assert "plain string" in s.assistant_turns[0].text


def test_truncated_last_line_is_skipped(tmp_path: Path) -> None:
    """Sessions are appended to live; the last line may be partial."""
    good = json.dumps(
        {"type": "user", "message": {"role": "user", "content": "hi"}}
    )
    p = tmp_path / "truncated.jsonl"
    p.write_text(good + "\n" + good[:30], encoding="utf-8")  # half a line at end
    s = load_session(p)
    assert len(s.user_turns) == 1


def test_handles_unicode_and_replacement(tmp_path: Path) -> None:
    p = tmp_path / "unicode.jsonl"
    payload = json.dumps(
        {"type": "user", "message": {"role": "user", "content": "héllo 🌍 — sí"}}
    )
    p.write_text(payload + "\n", encoding="utf-8")
    s = load_session(p)
    assert "🌍" in s.user_turns[0].text


@pytest.mark.parametrize(
    "model,expected_prefix",
    [
        ("claude-opus-4-7", "Opus"),
        ("claude-sonnet-4-6", "Sonnet"),
        ("claude-haiku-4-5", "Haiku"),
        ("claude-3-5-sonnet-20241022", "Sonnet"),
        ("not-a-real-model", "Sonnet"),  # default
        (None, "Sonnet"),
    ],
)
def test_pricing_for_known_model_prefixes(model, expected_prefix) -> None:
    from contextops.pricing import OPUS_4, SONNET_4, HAIKU_4, Pricing

    expected = {"Opus": OPUS_4, "Sonnet": SONNET_4, "Haiku": HAIKU_4}[expected_prefix]
    assert Pricing.for_model(model) is expected
