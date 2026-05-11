"""Performance benchmarks for the 4 new auditors.

Each test builds a 100-turn session containing the target waste pattern,
runs the auditor once, and asserts wall-clock time < 100 ms.
"""
from __future__ import annotations

import json
import time

from contextops.auditors.oversized_tool_outputs import OversizedToolOutputs
from contextops.auditors.duplicate_bash_runs import DuplicateBashRuns
from contextops.auditors.large_image_uploads import LargeImageUploads
from contextops.auditors.prompt_context_stuffing import PromptContextStuffing
from contextops.session import load_session


def test_perf_oversized_tool_outputs(write_session, builder):
    """S-06.1: OversizedToolOutputs processes 100-turn session in < 100 ms."""
    for _ in range(100):
        _, ids = builder.assistant(tool_uses=[("Bash", {"command": "find . -name '*.py'"})])
        builder.tool_result(ids[0], "x" * 10_000)
    path = write_session(builder)
    session = load_session(path)

    start = time.perf_counter()
    OversizedToolOutputs().run(session)
    elapsed_ms = (time.perf_counter() - start) * 1_000
    assert elapsed_ms < 100, f"OversizedToolOutputs took {elapsed_ms:.1f} ms (limit: 100 ms)"


def test_perf_duplicate_bash_runs(write_session, builder):
    """S-06.2: DuplicateBashRuns processes 100-turn session in < 100 ms."""
    for _ in range(50):
        _, ids1 = builder.assistant(tool_uses=[("Bash", {"command": "git log --oneline"})])
        builder.tool_result(ids1[0], "abc123 commit message\n" * 5)
        _, ids2 = builder.assistant(tool_uses=[("Bash", {"command": "git log --oneline"})])
        builder.tool_result(ids2[0], "abc123 commit message\n" * 5)
    path = write_session(builder)
    session = load_session(path)

    start = time.perf_counter()
    DuplicateBashRuns().run(session)
    elapsed_ms = (time.perf_counter() - start) * 1_000
    assert elapsed_ms < 100, f"DuplicateBashRuns took {elapsed_ms:.1f} ms (limit: 100 ms)"


def test_perf_large_image_uploads(tmp_path):
    """S-06.3: LargeImageUploads processes 100-turn session in < 100 ms.

    Uses raw JSONL construction because SessionBuilder does not support image blocks.
    """
    session_dir = tmp_path / "projects" / "bench"
    session_dir.mkdir(parents=True)
    session_file = session_dir / "session.jsonl"

    b64_data = "A" * 60_000
    turns = []
    for i in range(100):
        turns.append({
            "type": "user",
            "sessionId": "bench-session",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64_data,
                        },
                    }
                ],
            },
        })

    with session_file.open("w") as f:
        for turn in turns:
            f.write(json.dumps(turn) + "\n")

    session = load_session(session_file)

    start = time.perf_counter()
    LargeImageUploads().run(session)
    elapsed_ms = (time.perf_counter() - start) * 1_000
    assert elapsed_ms < 100, f"LargeImageUploads took {elapsed_ms:.1f} ms (limit: 100 ms)"


def test_perf_prompt_context_stuffing(write_session, builder):
    """S-06.4: PromptContextStuffing processes 100-turn session in < 100 ms."""
    log_line = "2026-05-11 10:23:01 INFO processing record {}\n"
    large_text = "".join(log_line.format(i) for i in range(600))  # ~22,000 chars
    short_text = "Please help me refactor this function."
    for _ in range(50):
        builder.user_text(large_text)
        builder.user_text(short_text)
    path = write_session(builder)
    session = load_session(path)

    start = time.perf_counter()
    PromptContextStuffing().run(session)
    elapsed_ms = (time.perf_counter() - start) * 1_000
    assert elapsed_ms < 100, f"PromptContextStuffing took {elapsed_ms:.1f} ms (limit: 100 ms)"
