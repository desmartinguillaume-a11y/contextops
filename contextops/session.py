"""Load Claude Code session JSONL files into a typed Session object."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------

def claude_home() -> Path:
    """Return the user's Claude Code home directory.

    Honours `$CLAUDE_HOME` (used by the test suite), then falls back to
    the standard `~/.claude/` location used on Linux and macOS.
    """
    env = os.environ.get("CLAUDE_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".claude"


def projects_dir() -> Path:
    return claude_home() / "projects"


def discover_sessions() -> list[Path]:
    """All `.jsonl` session files under `~/.claude/projects/`, newest first."""
    root = projects_dir()
    if not root.exists():
        return []
    files = [p for p in root.rglob("*.jsonl") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def latest_session() -> Path | None:
    sessions = discover_sessions()
    return sessions[0] if sessions else None


def find_project(name: str) -> Path | None:
    """Find the latest session whose project directory matches `name`.

    Project dirs look like `-home-user-contextops`. We match on substring
    after stripping leading dashes, case-insensitive.
    """
    needle = name.lower().lstrip("-/")
    candidates: list[Path] = []
    for session in discover_sessions():
        slug = session.parent.name.lower().lstrip("-")
        if needle in slug:
            candidates.append(session)
    return candidates[0] if candidates else None


# ---------------------------------------------------------------------------
# Typed events
# ---------------------------------------------------------------------------

@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @classmethod
    def from_dict(cls, d: dict | None) -> "Usage":
        if not d:
            return cls()
        return cls(
            input_tokens=int(d.get("input_tokens") or 0),
            output_tokens=int(d.get("output_tokens") or 0),
            cache_creation_input_tokens=int(d.get("cache_creation_input_tokens") or 0),
            cache_read_input_tokens=int(d.get("cache_read_input_tokens") or 0),
        )

    @property
    def total_input(self) -> int:
        return (
            self.input_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )

    @property
    def total(self) -> int:
        return self.total_input + self.output_tokens


@dataclass
class ToolUse:
    """An assistant `tool_use` content block."""

    id: str
    name: str
    input: dict[str, Any]
    turn_index: int  # which assistant turn (0-indexed) emitted it
    timestamp: str | None = None


@dataclass
class ToolResult:
    """A `tool_result` content block from a user turn."""

    tool_use_id: str
    content: str
    is_error: bool
    turn_index: int  # the user turn that delivered the result


@dataclass
class Turn:
    """One user or assistant event from the JSONL."""

    role: str  # "user" | "assistant"
    index: int
    text: str
    usage: Usage = field(default_factory=Usage)
    model: str | None = None
    is_sidechain: bool = False
    timestamp: str | None = None
    tool_uses: list[ToolUse] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Session:
    path: Path
    session_id: str
    turns: list[Turn]
    project_slug: str
    cwd: str | None
    model: str | None
    tool_definitions: list[str]  # names of tools exposed to the session

    # Convenience views ------------------------------------------------------

    @property
    def assistant_turns(self) -> list[Turn]:
        return [t for t in self.turns if t.role == "assistant"]

    @property
    def user_turns(self) -> list[Turn]:
        return [t for t in self.turns if t.role == "user"]

    @property
    def total_usage(self) -> Usage:
        u = Usage()
        for t in self.assistant_turns:
            u.input_tokens += t.usage.input_tokens
            u.output_tokens += t.usage.output_tokens
            u.cache_creation_input_tokens += t.usage.cache_creation_input_tokens
            u.cache_read_input_tokens += t.usage.cache_read_input_tokens
        return u

    def tool_calls(self, name: str | None = None) -> list[ToolUse]:
        out: list[ToolUse] = []
        for t in self.assistant_turns:
            for u in t.tool_uses:
                if name is None or u.name == name:
                    out.append(u)
        return out

    def result_for(self, tool_use_id: str) -> ToolResult | None:
        for t in self.user_turns:
            for r in t.tool_results:
                if r.tool_use_id == tool_use_id:
                    return r
        return None


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _coerce_text(content: Any) -> str:
    """Flatten Anthropic content (string OR list-of-blocks) to plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out: list[str] = []
        for block in content:
            if isinstance(block, str):
                out.append(block)
            elif isinstance(block, dict):
                t = block.get("type")
                if t == "text":
                    out.append(block.get("text") or "")
                elif t == "thinking":
                    # not user-visible, but useful for sizing
                    out.append(block.get("thinking") or "")
        return "\n".join(out)
    return str(content)


def _extract_tool_uses(blocks: Any, turn_index: int, ts: str | None) -> list[ToolUse]:
    if not isinstance(blocks, list):
        return []
    uses: list[ToolUse] = []
    for b in blocks:
        if isinstance(b, dict) and b.get("type") == "tool_use":
            uses.append(
                ToolUse(
                    id=b.get("id") or "",
                    name=b.get("name") or "",
                    input=b.get("input") or {},
                    turn_index=turn_index,
                    timestamp=ts,
                )
            )
    return uses


def _extract_tool_results(content: Any, turn_index: int) -> list[ToolResult]:
    if not isinstance(content, list):
        return []
    out: list[ToolResult] = []
    for b in content:
        if isinstance(b, dict) and b.get("type") == "tool_result":
            inner = b.get("content")
            text = _coerce_text(inner) if not isinstance(inner, str) else inner
            out.append(
                ToolResult(
                    tool_use_id=b.get("tool_use_id") or "",
                    content=text or "",
                    is_error=bool(b.get("is_error")),
                    turn_index=turn_index,
                )
            )
    return out


def _iter_events(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def load_session(path: str | Path) -> Session:
    path = Path(path).expanduser().resolve()
    turns: list[Turn] = []
    session_id = ""
    cwd: str | None = None
    model: str | None = None
    tool_definitions: list[str] = []

    user_idx = 0
    asst_idx = 0

    for event in _iter_events(path):
        etype = event.get("type")

        # Tool-availability deltas come through as attachments in Claude Code.
        if etype == "attachment":
            att = event.get("attachment") or {}
            if att.get("type") == "deferred_tools_delta":
                for n in att.get("addedNames") or []:
                    if n not in tool_definitions:
                        tool_definitions.append(n)
            continue

        if etype not in ("user", "assistant"):
            continue

        msg = event.get("message") or {}
        ts = event.get("timestamp")
        sid = event.get("sessionId")
        if sid and not session_id:
            session_id = sid
        if event.get("cwd") and not cwd:
            cwd = event["cwd"]

        is_sidechain = bool(event.get("isSidechain"))

        if etype == "assistant":
            content = msg.get("content")
            text = _coerce_text(content)
            usage = Usage.from_dict(msg.get("usage"))
            mdl = msg.get("model")
            if mdl and not model:
                model = mdl
            tool_uses = _extract_tool_uses(content, asst_idx, ts)
            turn = Turn(
                role="assistant",
                index=asst_idx,
                text=text,
                usage=usage,
                model=mdl,
                is_sidechain=is_sidechain,
                timestamp=ts,
                tool_uses=tool_uses,
                raw=event,
            )
            turns.append(turn)
            asst_idx += 1
        else:  # user
            content = msg.get("content")
            text = _coerce_text(content)
            tool_results = _extract_tool_results(content, user_idx)
            turn = Turn(
                role="user",
                index=user_idx,
                text=text,
                is_sidechain=is_sidechain,
                timestamp=ts,
                tool_results=tool_results,
                raw=event,
            )
            turns.append(turn)
            user_idx += 1

    project_slug = path.parent.name
    return Session(
        path=path,
        session_id=session_id or path.stem,
        turns=turns,
        project_slug=project_slug,
        cwd=cwd,
        model=model,
        tool_definitions=tool_definitions,
    )


# ---------------------------------------------------------------------------
# Helpers used by auditors
# ---------------------------------------------------------------------------

_PROJECT_SLUG_RE = re.compile(r"^-?(.+)$")


def humanize_project_slug(slug: str) -> str:
    """Convert `-home-user-contextops` → `/home/user/contextops`."""
    if not slug:
        return slug
    m = _PROJECT_SLUG_RE.match(slug)
    body = m.group(1) if m else slug
    return "/" + body.replace("-", "/")
