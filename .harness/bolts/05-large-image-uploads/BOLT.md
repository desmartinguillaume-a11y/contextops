# BOLT-05: large-image-uploads

## Overview

| Field | Value |
|-------|-------|
| Bolt | BOLT-05 |
| Group | Group 3: Complex Auditor + Benchmarks (sequential) |
| Stories | US-03, US-08, US-09 |
| Depends On | BOLT-01 |
| Estimated Tasks | 2 |
| Mode | standard |

## Objective

Replace the stub body of `LargeImageUploads.run()` with a full implementation that detects oversized base64 image blocks (>50,000 chars) and cross-turn duplicate images in raw session turn data, and write a comprehensive unit test file covering all 9 acceptance scenarios from F-03.

## Context

The stub class already exists in `contextops/auditors/large_image_uploads.py` from BOLT-01.

This auditor is placed in a separate group (Group 3, sequential) because it requires direct JSONL raw-turn access, which is more complex than the three Group 2 auditors. The `_coerce_text` / `_extract_tool_results` pipeline in `session.py` silently discards `type=="image"` content blocks, so this auditor must bypass the typed layer entirely and read `turn.raw` directly.

Access pattern (fully defensive):
```python
content = (turn.raw or {}).get("message", {}).get("content") or []
if not isinstance(content, list):
    continue
for block in content:
    if not isinstance(block, dict):
        continue
    if block.get("type") != "image":
        continue
    source = block.get("source") or {}
    if source.get("type") != "base64":
        continue
    data = source.get("data")
    if not isinstance(data, str):
        continue
    # data is a valid base64 string
```

The auditor emits two types of findings:
1. **Oversized image**: `len(data) > IMAGE_THRESHOLD` (50,000 chars). One finding per oversized image block.
2. **Duplicate image**: same base64 string appearing in two or more distinct turns. One finding per distinct duplicated base64 string.

Both finding types can be emitted for the same image block (if the same large image is in multiple turns, it gets both an oversized finding and a duplicate finding — see S-03.2).

Token estimation: `max(1, len(data) // 4)`.

`fix_hint` for oversized: `"Resize the screenshot to under 512px on the longest side, or use the Files API instead of base64 inline upload."`
`fix_hint` for duplicate: `"This image was sent in N turns. Send it once, or reference the Files API URI across turns."` (substitute actual count for N).

Test file construction: The `SessionBuilder` DSL does not support image blocks. Tests must construct raw JSONL dicts directly and write them to a temp file using `write_session` fixture or a raw file write, then load with `load_session()`. See notes below for the required JSONL line structure.

## Research

- `turn.raw` is the raw parsed dict for one JSONL event. Its structure: `{"type": "...", "message": {"role": "...", "content": [...blocks...]}, ...}`.
- Image block structure: `{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "<base64-string>"}}`.
- `turn.raw` may be `None` for synthesized/internal turns — always guard with `(turn.raw or {})`.
- Image blocks can appear in both user and assistant turns. The auditor should check all turns, not just user turns.
- Cross-turn duplicate detection: track `seen: dict[str, list[int]]` mapping the base64 data string (or its hash for memory efficiency) to list of turn indices where it appeared. After iterating all turns, emit duplicate findings for any data appearing in ≥2 distinct turns.
- For memory-constrained sessions with many large images, using `hashlib.md5(data.encode()).hexdigest()` instead of the raw data string as the dict key avoids storing large strings. However, the full data string must be kept for the length check — so cache the length alongside the hash.

## Tasks

<tasks>
<task id="1" name="Implement LargeImageUploads.run()" file="contextops/auditors/large_image_uploads.py">
Replace the stub `run()` with the full implementation. Key design:
- Two-pass approach: first pass collects all image data items (with their turn indices and lengths), second pass emits findings.
- Or single-pass: emit oversized findings immediately, accumulate seen data for duplicate detection, emit duplicate findings at the end.

Single-pass approach (recommended):

```python
"""Auditor — large image uploads (FinOps: rightsizing)."""
from __future__ import annotations

import hashlib
import logging

from . import Category, Finding
from ..pricing import Pricing, estimate_tokens
from ..session import Session

log = logging.getLogger(__name__)

IMAGE_THRESHOLD = 50_000  # base64 chars


class LargeImageUploads:
    name = "large_image_uploads"
    title = "Large image uploads"
    category = Category.RIGHTSIZING

    def run(self, session: Session) -> list[Finding]:
        pricing = Pricing.for_model(session.model)
        findings: list[Finding] = []

        # hash → list of (turn_index, data_len) for duplicate detection
        seen: dict[str, list[tuple[int, int]]] = {}

        for turn in session.turns:
            try:
                raw = turn.raw or {}
                content = raw.get("message", {}).get("content") or []
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "image":
                        continue
                    source = block.get("source") or {}
                    if source.get("type") != "base64":
                        continue
                    data = source.get("data")
                    if not isinstance(data, str):
                        log.debug(
                            "large_image_uploads: non-string data field in turn %s",
                            turn.turn_index,
                        )
                        continue
                    data_len = len(data)
                    data_hash = hashlib.md5(data.encode(), usedforsecurity=False).hexdigest()

                    seen.setdefault(data_hash, []).append((turn.turn_index, data_len))

                    if data_len > IMAGE_THRESHOLD:
                        tokens = max(1, data_len // 4)
                        dollars = pricing.dollars(input_tokens=tokens)
                        findings.append(
                            Finding(
                                auditor=self.name,
                                title=self.title,
                                category=self.category,
                                wasted_tokens=tokens,
                                wasted_dollars=dollars,
                                recommendation=(
                                    f"Turn {turn.turn_index} contains a base64 image "
                                    f"of [bold]{data_len:,} chars[/bold] "
                                    f"(~{tokens:,} tokens, ${dollars:.4f}). "
                                    f"Large images inflate context on every refill."
                                ),
                                methodology=(
                                    "Scanned turn.raw message content for base64 "
                                    f"image blocks exceeding {IMAGE_THRESHOLD:,} chars."
                                ),
                                evidence=[
                                    f"turn {turn.turn_index}: {data_len:,} chars, "
                                    f"~{tokens:,} tokens, "
                                    f"id={data[:40]!r}"
                                ],
                                fix_hint=(
                                    "Resize the screenshot to under 512px on the "
                                    "longest side, or use the Files API instead of "
                                    "base64 inline upload."
                                ),
                            )
                        )
            except Exception:
                log.debug(
                    "large_image_uploads: error processing turn %s",
                    getattr(turn, "turn_index", "?"),
                    exc_info=True,
                )

        # Duplicate detection: emit one finding per hash seen in ≥2 turns
        for data_hash, occurrences in seen.items():
            if len(occurrences) < 2:
                continue
            turn_indices = [idx for idx, _ in occurrences]
            # Use data_len from first occurrence for token estimate
            data_len = occurrences[0][1]
            # wasted tokens = (count - 1) redundant copies
            redundant_copies = len(occurrences) - 1
            tokens = max(1, data_len // 4) * redundant_copies
            dollars = pricing.dollars(input_tokens=tokens)
            findings.append(
                Finding(
                    auditor=self.name,
                    title=self.title,
                    category=self.category,
                    wasted_tokens=tokens,
                    wasted_dollars=dollars,
                    recommendation=(
                        f"The same image appears in [bold]{len(occurrences)} turns[/bold] "
                        f"({', '.join(str(i) for i in turn_indices)}). "
                        f"Each copy costs ~{max(1, data_len // 4):,} tokens."
                    ),
                    methodology=(
                        "Compared MD5 hashes of base64 image data across all turns; "
                        "flagged hashes seen in 2+ distinct turns."
                    ),
                    evidence=[f"turn {idx}" for idx in turn_indices],
                    fix_hint=(
                        f"This image was sent in {len(occurrences)} turns. "
                        f"Send it once, or reference the Files API URI across turns."
                    ),
                )
            )

        findings.sort(key=lambda f: f.wasted_tokens, reverse=True)
        return findings
```

`usedforsecurity=False` in `hashlib.md5()` is required for Python 3.9+ on systems with FIPS mode enabled; it is always available in Python 3.10+ (which is the minimum for this project).
</task>

<task id="2" name="Write unit tests" file="tests/test_large_image_uploads.py" depends="1">
Create `tests/test_large_image_uploads.py` with one test function per scenario from F-03 (S-03.1 through S-03.9).

Since `SessionBuilder` does not support image blocks, tests must construct raw JSONL. Use the `tmp_path` pytest fixture to write JSONL files and `load_session()` to load them. The CLAUDE_HOME override (`monkeypatch.setenv("CLAUDE_HOME", str(tmp_path))`) lets `discover_sessions()` find the file, but for individual auditor tests it's sufficient to call `load_session(path)` directly.

JSONL line format for a session with one turn containing an image block:
```python
import json, pathlib

def write_image_session(tmp_path, turns_data):
    """Write a minimal JSONL session file with raw turn dicts."""
    session_dir = tmp_path / "projects" / "test-project"
    session_dir.mkdir(parents=True)
    session_file = session_dir / "session.jsonl"
    with session_file.open("w") as f:
        for turn_dict in turns_data:
            f.write(json.dumps(turn_dict) + "\n")
    return session_file
```

Each turn dict must match the JSONL schema that `load_session()` expects. Inspect `contextops/session.py` to understand the exact schema, then construct minimal valid dicts. The key shape needed:
```python
{"type": "message", "message": {"role": "user", "content": [
    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "A" * 60000}}
]}}
```

Test functions to write:
- `test_s03_1_single_large_image`: turn 2 with 60,000-char base64 → 1 finding, auditor=="large_image_uploads", wasted_tokens==15000, wasted_dollars>0, fix_hint contains "Resize" or "Files API", evidence references turn 2
- `test_s03_2_same_large_image_two_turns`: turns 1 and 3 with same 55,000-char base64 → ≥2 findings (1 oversized for each turn + 1 duplicate); duplicate finding's fix_hint mentions "2"
- `test_s03_3_image_below_threshold`: turn with 300-char base64 → empty list
- `test_s03_4_url_source_type_skipped`: image block with source.type=="url" (no "data" field) → empty list, no exception
- `test_s03_5_content_is_string_not_list`: turn where message.content is a plain string → empty list, no exception
- `test_s03_6_image_block_missing_source_key`: content block with type=="image" but no "source" key → empty list, no exception
- `test_s03_7_no_image_blocks`: session with only text blocks → empty list
- `test_s03_8_multiple_different_large_images_same_turn`: turn 1 with two distinct 60,000-char image blocks → exactly 2 findings (one per oversized image; no duplicate because different content)
- `test_s03_9_data_field_is_integer`: image block where source.data is set to 42 (integer not string) → empty list, no unhandled exception

Import: `from contextops.auditors.large_image_uploads import LargeImageUploads` and `from contextops.session import load_session`.

After writing tests, run `.venv/bin/pytest tests/test_large_image_uploads.py -v` to confirm all pass.
</task>
</tasks>

<mode>standard</mode>

## Acceptance Criteria

- [ ] AC-1 (from S-03.1): **Given** a session JSONL where one turn contains an image block with base64 data of length 60,000 chars, **When** `LargeImageUploads().run(session)` is called, **Then** exactly 1 `Finding` is returned with `finding.auditor == "large_image_uploads"`, `finding.wasted_tokens == 15000`, `finding.wasted_dollars > 0.0`, `finding.fix_hint` contains `"Resize"` or `"Files API"`, and `finding.evidence[0]` references the affected turn index.

- [ ] AC-2 (from S-03.2): **Given** a session JSONL where two turns contain the same base64 string of length 55,000 chars, **When** `LargeImageUploads().run(session)` is called, **Then** at least 2 `Finding` objects are returned — one covering the oversized image (wasted_tokens >= 13750) and one covering the duplication (fix_hint references the number `2` or "2 turns").

- [ ] AC-3 (from S-03.3): **Given** a session JSONL with one image block whose base64 data is 300 chars, **When** `LargeImageUploads().run(session)` is called, **Then** the returned list is `[]`.

- [ ] AC-4 (from S-03.4): **Given** a session JSONL with an image block with `source.type == "url"` and no `data` field, **When** `LargeImageUploads().run(session)` is called, **Then** the returned list is `[]` and no exception is raised.

- [ ] AC-5 (from S-03.5): **Given** a session JSONL where `message.content` is a plain string `"Hello world"`, **When** `LargeImageUploads().run(session)` is called, **Then** the returned list is `[]` and no exception is raised.

- [ ] AC-6 (from S-03.6): **Given** a session JSONL where one content block has `"type": "image"` but no `"source"` key, **When** `LargeImageUploads().run(session)` is called, **Then** the returned list is `[]` and no exception is raised.

- [ ] AC-7 (from S-03.7): **Given** a session JSONL with only text blocks in all message content lists, **When** `LargeImageUploads().run(session)` is called, **Then** the returned list is `[]`.

- [ ] AC-8 (from S-03.8): **Given** a session JSONL where one turn contains two distinct image blocks both with 60,000-char base64 data (different content), **When** `LargeImageUploads().run(session)` is called, **Then** exactly 2 `Finding` objects are returned — one per oversized image.

- [ ] AC-9 (from S-03.9): **Given** a session JSONL where an image block has `source.data` set to the integer `42`, **When** `LargeImageUploads().run(session)` is called, **Then** the returned list is `[]` and no unhandled exception propagates.

## Definition of Done

- [ ] All ACs verified with evidence (test output)
- [ ] No stub or placeholder code in production paths
- [ ] Unit tests written and passing (`tests/test_large_image_uploads.py` — 9 test functions)
- [ ] No hardcoded secrets or credentials in source code
- [ ] Error cases handled (non-list content, missing source, non-string data, url-type images)
- [ ] Code follows existing project patterns

## Test Coverage

| Layer | What it tests | Required? |
|-------|--------------|-----------|
| Unit | All 9 F-03 scenarios via `tests/test_large_image_uploads.py` | Yes |
| Integration | Not required | No |
| E2E | Not required | No |

## Notes

- `usedforsecurity=False` is required in `hashlib.md5()` for FIPS compliance on Python >=3.9. Always include it.
- Tests cannot use `SessionBuilder` for image data — they must construct raw JSONL dicts. Read `contextops/session.py` to understand the exact JSONL schema that `load_session()` parses, particularly what fields are required on each line for `Turn` creation.
- For S-03.2: the same base64 string in two turns should produce both an oversized finding (per turn or once) AND a duplicate finding. The exact count depends on implementation: if oversized is emitted once per oversized block (one per occurrence), S-03.2 produces 2 oversized + 1 duplicate = 3 findings, and the AC says "at least 2". Align the test to match actual behavior.
- `hashlib.md5` is used for memory efficiency; storing the full 55,000-char base64 string as a dict key is wasteful for large images. The hash is sufficient for deduplication.

---
*Generated by Agent Harness — Design Plan Phase*
