#!/usr/bin/env python3
"""ContextOps session-format inspector.

Run this on your laptop (where you actually use Claude Code locally), paste
the output back. Self-contained, stdlib-only, no install required.

It looks for Claude Code session JSONL files in the usual places and
reports:
  - which directory layout you have
  - what event types appear, and how often
  - what tool names actually get invoked (via tool_use blocks)
  - whether the session declares its tool inventory anywhere we can find
    (attachment.deferred_tools_delta, system messages, etc.)
  - one redacted example of each event type
  - one redacted example of an assistant message's `usage` block

Nothing leaves your machine. The output is purely local.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


# -- Discovery ---------------------------------------------------------------

CANDIDATE_ROOTS = [
    Path.home() / ".claude" / "projects",
    Path.home() / ".claude" / "sessions",
    Path.home() / ".config" / "claude" / "projects",
    Path.home() / "Library" / "Application Support" / "Claude" / "projects",
    Path.home() / "Library" / "Application Support" / "Claude",
]


def find_sessions() -> tuple[Path | None, list[Path]]:
    for root in CANDIDATE_ROOTS:
        if not root.exists():
            continue
        files = sorted(
            (p for p in root.rglob("*.jsonl") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if files:
            return root, files
    return None, []


# -- Redaction ---------------------------------------------------------------

USER_RE = re.compile(rf"/(home|Users)/[^/\s\"']+", re.IGNORECASE)


def redact(s: str) -> str:
    s = USER_RE.sub("/user", s)
    return s


def truncate(s: str, n: int = 240) -> str:
    if len(s) <= n:
        return s
    return s[:n] + f"… [+{len(s) - n} chars]"


def short_dump(obj: Any, n: int = 240) -> str:
    return truncate(redact(json.dumps(obj, default=str)), n)


# -- Inspection --------------------------------------------------------------

def inspect_session(path: Path, max_events: int = 5000) -> dict:
    type_counts: Counter[str] = Counter()
    tool_calls: Counter[str] = Counter()
    declared_tools: Counter[str] = Counter()
    attachment_subtypes: Counter[str] = Counter()
    examples: dict[str, dict] = {}
    sample_usage: dict | None = None
    sample_assistant_top_keys: set[str] = set()
    sample_user_top_keys: set[str] = set()
    user_content_shapes: Counter[str] = Counter()
    tool_result_content_shapes: Counter[str] = Counter()
    models: Counter[str] = Counter()
    versions: Counter[str] = Counter()

    n = 0
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            n += 1
            if n > max_events:
                break
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                type_counts["__malformed__"] += 1
                continue

            t = evt.get("type", "__no_type__")
            type_counts[t] += 1

            if t not in examples:
                examples[t] = evt

            if t == "assistant":
                sample_assistant_top_keys.update(evt.keys())
                msg = evt.get("message") or {}
                if msg.get("model"):
                    models[msg["model"]] += 1
                if evt.get("version"):
                    versions[evt["version"]] += 1
                if sample_usage is None and msg.get("usage"):
                    sample_usage = msg["usage"]
                content = msg.get("content")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            tool_calls[block.get("name", "?")] += 1

            if t == "user":
                sample_user_top_keys.update(evt.keys())
                msg = evt.get("message") or {}
                content = msg.get("content")
                shape = type(content).__name__
                user_content_shapes[shape] += 1
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            inner = block.get("content")
                            tool_result_content_shapes[type(inner).__name__] += 1

            if t == "attachment":
                att = evt.get("attachment") or {}
                sub = att.get("type", "?")
                attachment_subtypes[sub] += 1
                if sub == "deferred_tools_delta":
                    for name in att.get("addedNames") or []:
                        declared_tools[name] += 1

            # Some Claude Code versions might use `system` events to declare tools;
            # capture anything that looks like a tool list.
            if t in ("system", "init", "session-start", "tool-list"):
                for k in ("tools", "toolDefinitions", "availableTools"):
                    v = evt.get(k)
                    if isinstance(v, list):
                        for it in v:
                            name = it if isinstance(it, str) else (it or {}).get("name")
                            if name:
                                declared_tools[name] += 1

    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "events_scanned": n,
        "type_counts": dict(type_counts),
        "tool_calls": dict(tool_calls),
        "declared_tools_count": len(declared_tools),
        "declared_tools_sample": dict(list(declared_tools.items())[:8]),
        "attachment_subtypes": dict(attachment_subtypes),
        "models": dict(models),
        "versions": dict(versions),
        "user_content_shapes": dict(user_content_shapes),
        "tool_result_content_shapes": dict(tool_result_content_shapes),
        "assistant_top_keys": sorted(sample_assistant_top_keys),
        "user_top_keys": sorted(sample_user_top_keys),
        "sample_usage": sample_usage,
        "examples": {
            t: short_dump(e, 320) for t, e in examples.items()
        },
    }


# -- Output ------------------------------------------------------------------

def print_report(root: Path, sessions: list[Path], reports: list[dict]) -> None:
    print("=" * 72)
    print("ContextOps session-format inspector")
    print("=" * 72)
    print(f"Detected session root: {root}")
    print(f"Found sessions: {len(sessions)} (.jsonl files)")
    print(f"Inspecting most recent {len(reports)}.")
    print()

    for i, r in enumerate(reports):
        print(f"--- Session #{i + 1} ---")
        print(f"  path:        {redact(r['path'])}")
        print(f"  size_bytes:  {r['size_bytes']:,}")
        print(f"  events:      {r['events_scanned']:,}")
        print(f"  versions:    {r['versions']}")
        print(f"  models:      {r['models']}")
        print(f"  type_counts: {r['type_counts']}")
        print(f"  attachment_subtypes: {r['attachment_subtypes']}")
        print(f"  declared_tools_count: {r['declared_tools_count']}")
        print(f"  declared_tools_sample: {r['declared_tools_sample']}")
        print(f"  tool_calls:  {r['tool_calls']}")
        print(f"  user_content_shapes: {r['user_content_shapes']}")
        print(f"  tool_result_content_shapes: {r['tool_result_content_shapes']}")
        print(f"  assistant_top_keys: {r['assistant_top_keys']}")
        print(f"  user_top_keys: {r['user_top_keys']}")
        print(f"  sample_usage: {r['sample_usage']}")
        print(f"  examples:")
        for t, ex in r["examples"].items():
            print(f"    [{t}] {ex}")
        print()


def main() -> int:
    root, sessions = find_sessions()
    if root is None:
        print("No Claude Code session directory found in any of:")
        for c in CANDIDATE_ROOTS:
            print(f"  {c}")
        print()
        print("If your sessions live elsewhere, pass a path:")
        print(f"  python {sys.argv[0]} /path/to/sessions/dir/")
        return 1

    if len(sys.argv) > 1:
        root = Path(sys.argv[1]).expanduser()
        sessions = sorted(
            (p for p in root.rglob("*.jsonl") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

    chosen = sessions[:3]
    reports = [inspect_session(p) for p in chosen]
    print_report(root, sessions, reports)
    return 0


if __name__ == "__main__":
    sys.exit(main())
