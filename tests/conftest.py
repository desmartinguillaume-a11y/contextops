"""Shared test helpers: synthetic Claude Code session builder."""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any, Iterator

import pytest


_ID_COUNTERS: dict[str, Iterator[int]] = {
    "msg": itertools.count(1),
    "tool": itertools.count(1),
    "uuid": itertools.count(1),
}


def _next(kind: str) -> str:
    n = next(_ID_COUNTERS[kind])
    return f"{kind}_{n:08d}"


class SessionBuilder:
    """Tiny DSL for assembling a JSONL session file in tests."""

    def __init__(self, *, model: str = "claude-sonnet-4-6") -> None:
        self.events: list[dict[str, Any]] = []
        self.session_id = "test-session"
        self.model = model
        self._asst_idx = 0
        self._user_idx = 0
        self._pending_assistant_blocks: list[dict[str, Any]] = []
        self._pending_user_blocks: list[dict[str, Any]] = []

    # User turns ---------------------------------------------------------

    def user_text(self, text: str) -> "SessionBuilder":
        self.events.append(
            {
                "type": "user",
                "uuid": _next("uuid"),
                "sessionId": self.session_id,
                "message": {"role": "user", "content": text},
            }
        )
        self._user_idx += 1
        return self

    def tool_result(self, tool_use_id: str, content: str, *, is_error: bool = False) -> "SessionBuilder":
        self.events.append(
            {
                "type": "user",
                "uuid": _next("uuid"),
                "sessionId": self.session_id,
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "is_error": is_error,
                            "content": content,
                        }
                    ],
                },
            }
        )
        self._user_idx += 1
        return self

    # Assistant turns ----------------------------------------------------

    def assistant(
        self,
        *,
        text: str = "",
        tool_uses: list[tuple[str, dict]] | None = None,
        usage: dict | None = None,
        cwd: str | None = None,
    ) -> tuple["SessionBuilder", list[str]]:
        """Append an assistant turn. Returns (self, list of tool_use_ids)."""
        content: list[dict[str, Any]] = []
        if text:
            content.append({"type": "text", "text": text})
        ids: list[str] = []
        for name, args in tool_uses or []:
            tid = _next("tool")
            ids.append(tid)
            content.append({"type": "tool_use", "id": tid, "name": name, "input": args})

        evt = {
            "type": "assistant",
            "uuid": _next("uuid"),
            "sessionId": self.session_id,
            "cwd": cwd,
            "message": {
                "role": "assistant",
                "type": "message",
                "model": self.model,
                "id": _next("msg"),
                "content": content,
                "usage": usage or {"input_tokens": 100, "output_tokens": 50},
            },
        }
        self.events.append(evt)
        self._asst_idx += 1
        return self, ids

    def attach_tools(self, names: list[str]) -> "SessionBuilder":
        self.events.append(
            {
                "type": "attachment",
                "uuid": _next("uuid"),
                "attachment": {
                    "type": "deferred_tools_delta",
                    "addedNames": names,
                    "addedLines": names,
                },
            }
        )
        return self

    # Materialization ----------------------------------------------------

    def write(self, path: Path) -> Path:
        path.write_text("\n".join(json.dumps(e) for e in self.events) + "\n")
        return path


@pytest.fixture
def builder() -> SessionBuilder:
    # Reset counters per test for stable IDs.
    _ID_COUNTERS["msg"] = itertools.count(1)
    _ID_COUNTERS["tool"] = itertools.count(1)
    _ID_COUNTERS["uuid"] = itertools.count(1)
    return SessionBuilder()


@pytest.fixture
def write_session(tmp_path: Path):
    def _write(b: SessionBuilder, name: str = "session.jsonl") -> Path:
        return b.write(tmp_path / name)

    return _write
