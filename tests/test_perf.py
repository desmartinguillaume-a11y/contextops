"""Performance smoke test on a synthetic large session.

Real users have multi-megabyte JSONL transcripts. The whole audit pipeline
should run on a 100K-event session in well under a few seconds, and we
should not blow up memory by holding multiple copies.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from contextops.auditors import all_auditors
from contextops.session import load_session


def _build_large_session(path: Path, n_turns: int = 200) -> Path:
    """Write a session with `n_turns` assistant turns interleaved with tool results.

    Includes file reads that repeat (so the auditors actually do work),
    moderately big tool outputs, and a mix of tool kinds.
    """
    body = "x" * 4_000  # ~1K tokens
    listing = "\n".join(f"file_{i}.py" for i in range(80))

    events: list[dict] = []
    for i in range(n_turns):
        ids = []
        if i % 3 == 0:
            tool_id = f"tu_{i}"
            ids.append(tool_id)
            events.append(
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "model": "claude-sonnet-4-6",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": tool_id,
                                "name": "Read",
                                "input": {"file_path": f"/repo/src/file_{i % 5}.py"},
                            }
                        ],
                        "usage": {
                            "input_tokens": 200,
                            "output_tokens": 80,
                            "cache_read_input_tokens": 1500,
                        },
                    },
                }
            )
            events.append(
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [
                            {"type": "tool_result", "tool_use_id": tool_id, "content": body}
                        ],
                    },
                }
            )
        elif i % 5 == 0:
            tool_id = f"ls_{i}"
            events.append(
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "model": "claude-sonnet-4-6",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": tool_id,
                                "name": "LS",
                                "input": {"path": "/repo/src"},
                            }
                        ],
                        "usage": {"input_tokens": 100, "output_tokens": 40},
                    },
                }
            )
            events.append(
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [
                            {"type": "tool_result", "tool_use_id": tool_id, "content": listing}
                        ],
                    },
                }
            )
        else:
            events.append(
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "model": "claude-sonnet-4-6",
                        "content": [{"type": "text", "text": f"thinking step {i}"}],
                        "usage": {"input_tokens": 60, "output_tokens": 30},
                    },
                }
            )

    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return path


def test_audit_under_three_seconds_on_large_session(tmp_path: Path) -> None:
    path = _build_large_session(tmp_path / "big.jsonl", n_turns=4000)
    size_mb = path.stat().st_size / 1024 / 1024
    assert size_mb > 5, f"fixture too small to be a meaningful perf test ({size_mb:.1f} MB)"

    t0 = time.perf_counter()
    s = load_session(path)
    t_load = time.perf_counter() - t0

    t0 = time.perf_counter()
    for a in all_auditors():
        a.run(s)
    t_audit = time.perf_counter() - t0

    total = t_load + t_audit
    # Generous budget: this runs on CI hardware too. Real local laptops are 5–10x faster.
    assert total < 3.0, (
        f"audit too slow on {size_mb:.1f} MB session: "
        f"load={t_load:.2f}s audit={t_audit:.2f}s total={total:.2f}s"
    )
