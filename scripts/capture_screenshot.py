#!/usr/bin/env python3
"""Render `contextops analyze` to a static SVG for the README.

Why SVG and not PNG: GitHub renders SVG inline, the file is a tenth the
size of a PNG, the text stays selectable, and we don't need a Cairo /
ImageMagick toolchain on macOS.

Usage (from the repo root):

    # Latest session, default output path
    python scripts/capture_screenshot.py

    # Specific project (substring match against project slug)
    python scripts/capture_screenshot.py --project myrepo

    # Specific session JSONL
    python scripts/capture_screenshot.py ~/.claude/projects/-home-me-myrepo/abc123.jsonl

    # Custom output path
    python scripts/capture_screenshot.py --out docs/hero.svg

The README's screenshot placeholder lives at:
    <!-- TODO: replace this comment with ![ContextOps report](docs/screenshot.png) -->
After capturing, replace that comment with:
    ![ContextOps report](docs/screenshot.svg)

Then commit `docs/screenshot.svg` and the README change together.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console

from contextops.auditors import all_auditors
from contextops.report import render_report
from contextops.session import (
    discover_sessions,
    find_project,
    latest_session,
    load_session,
)


def _resolve_session_path(args: argparse.Namespace) -> Path:
    if args.session_path:
        return Path(args.session_path).expanduser().resolve()

    if args.project:
        match = find_project(args.project)
        if not match:
            sys.exit(f"No project found matching '{args.project}'.")
        return match

    latest = latest_session()
    if latest:
        return latest

    sessions = discover_sessions()
    if not sessions:
        sys.exit(
            "No Claude Code sessions found under ~/.claude/projects/. "
            "Run Claude Code at least once before capturing a screenshot."
        )
    return sessions[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "session_path",
        nargs="?",
        help="Path to a session JSONL. Defaults to the most recent.",
    )
    parser.add_argument(
        "--project",
        "-p",
        help="Project slug substring; latest session in that project is used.",
    )
    parser.add_argument(
        "--out",
        default="docs/screenshot.svg",
        help="Where to write the SVG (default: docs/screenshot.svg).",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=100,
        help="Console width in columns (default: 100). Wider = more readable on retina.",
    )
    parser.add_argument(
        "--title",
        default="contextops analyze",
        help="Title shown in the SVG window chrome.",
    )
    args = parser.parse_args()

    path = _resolve_session_path(args)
    session = load_session(path)

    findings: list = []
    for auditor in all_auditors():
        findings.extend(auditor.run(session))

    console = Console(record=True, width=args.width)
    render_report(session, findings, console=console)

    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    console.save_svg(str(out_path), title=args.title)

    print(f"Wrote {out_path}")
    print(
        f"Session: {path}\n"
        f"Project: {session.project_slug}  ·  "
        f"Turns: {len(session.assistant_turns)}  ·  "
        f"Findings: {len(findings)}"
    )
    print("\nNext: in README.md, replace the screenshot TODO comment with:")
    print(f"    ![ContextOps report]({Path(args.out).as_posix()})")


if __name__ == "__main__":
    main()
