# BOLT-06: benchmark-tests — Complete

## Summary

Created `tests/test_perf_new_auditors.py` with 4 benchmark test functions, one per new auditor (OversizedToolOutputs, DuplicateBashRuns, LargeImageUploads, PromptContextStuffing). Each test builds a synthetic 100-turn session containing the target waste pattern, times the auditor with `time.perf_counter`, and asserts elapsed time is under 100 ms. All 4 tests pass in approximately 60 ms total on local hardware.

## Tasks Completed

| # | Task | Status |
|---|------|--------|
| 1 | Write benchmark test file | Done |

## Commits

- `feat(bolt-06): add performance benchmark tests for the 4 new auditors`

## Files Created/Modified

- `tests/test_perf_new_auditors.py` — Created: 4 benchmark tests using stdlib `time.perf_counter`, `load_session`, and existing fixtures from conftest.py

## Deviations

- The bolt spec template showed `builder.tool_use(...)`, `builder.tool_result(content)`, and `builder.human(text)` method names that do not exist in the actual `SessionBuilder` DSL. The actual DSL uses `builder.assistant(tool_uses=[(name, args)])` which returns `(self, ids)`, `builder.tool_result(tool_use_id, content)` (requires the ID from the assistant call), and `builder.user_text(text)`. The implementation was adjusted accordingly.
- `write_session(builder)` returns a `Path`, not a `Session`. Each test calls `load_session(path)` on the returned path before timing (the timing starts only on the auditor's `run()` call, not on I/O).

## Issues Discovered

None.

## Acceptance Criteria

- [x] AC-1: `test_perf_oversized_tool_outputs` — 100 assistant turns each with a Bash tool_use (10,000-char result); `OversizedToolOutputs().run(session)` completes in < 100 ms. Verified by pytest pass.
- [x] AC-2: `test_perf_duplicate_bash_runs` — 50 pairs of identical `git log --oneline` Bash calls (100 total); `DuplicateBashRuns().run(session)` completes in < 100 ms. Verified by pytest pass.
- [x] AC-3: `test_perf_large_image_uploads` — 100 raw JSONL turns each with a 60,000-char base64 image block; `LargeImageUploads().run(session)` completes in < 100 ms. Verified by pytest pass.
- [x] AC-4: `test_perf_prompt_context_stuffing` — 50 user turns with ~22,000-char timestamp-prefixed log text + 50 short turns; `PromptContextStuffing().run(session)` completes in < 100 ms. Verified by pytest pass.
- [x] AC-5: No new packages introduced — only stdlib `time`, `json`, existing `contextops` internals, and existing pytest fixtures are used.
- [x] AC-6: `pytest tests/test_perf_new_auditors.py -v` collects and passes all 4 test functions with no fixture errors or unknown mark warnings. Evidence: `4 passed in 0.06s`.
