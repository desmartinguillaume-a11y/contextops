# BOLT-04: prompt-context-stuffing — Complete

## Summary

Implemented `PromptContextStuffing.run()` replacing the stub body with full signal detection logic (stack trace keywords, timestamp sequences, high line-prefix repetition) for user turns exceeding 5,000 estimated tokens. Wrote 10 unit tests covering all F-04 acceptance scenarios (S-04.1 through S-04.10).

## Tasks Completed

| # | Task | Status |
|---|------|--------|
| 1 | Implement PromptContextStuffing.run() | Done |
| 2 | Write unit tests (tests/test_prompt_context_stuffing.py) | Done |

## Commits

- `feat(bolt-04): implement PromptContextStuffing auditor with 10 unit tests`

## Files Created/Modified

- `contextops/auditors/prompt_context_stuffing.py` — Modified: replaced stub `run()` with full implementation including `_detect_signal()` helper and three structural signal checks
- `tests/test_prompt_context_stuffing.py` — Created: 10 unit tests covering all F-04 scenarios

## Deviations

- The bolt spec uses `turn.turn_index` in the evidence string, but the `Turn` dataclass in `session.py` uses `turn.index` (as confirmed by reading the loader code and other auditors). Used `turn.index` throughout to match the actual data model.
- The `estimate_tokens("")` function returns `0` (not `1` as the spec notes), because the implementation has `if not text: return 0`. This is irrelevant to behavior since 0 < 5000 threshold, but the spec comment was slightly inaccurate.

## Issues Discovered

None.

## Acceptance Criteria

- [x] AC-1 (S-04.1): 25,000-char stack trace blob → 1 finding, auditor=="prompt_context_stuffing", wasted_tokens==6250, fix_hint contains "file", evidence contains "stack_trace" — verified by `test_s04_1_stack_trace_signal`
- [x] AC-2 (S-04.2): 24,000-char timestamp log → 1 finding, wasted_tokens==6000, evidence contains "timestamp" — verified by `test_s04_2_timestamp_log_lines`
- [x] AC-3 (S-04.3): 22,000-char 4-space-indented blob → 1 finding, evidence contains "prefix"/"repetition" — verified by `test_s04_3_high_prefix_repetition`
- [x] AC-4 (S-04.4): 22,000-char prose → empty list — verified by `test_s04_4_large_prose_no_signal`
- [x] AC-5 (S-04.5): tool-result delivery turn → empty list — verified by `test_s04_5_tool_result_delivery_skipped`
- [x] AC-6 (S-04.6): 38-char message → empty list — verified by `test_s04_6_below_threshold`
- [x] AC-7 (S-04.7): two stuffed turns → exactly 2 findings — verified by `test_s04_7_two_stuffed_turns`
- [x] AC-8 (S-04.8): only assistant turns → empty list — verified by `test_s04_8_no_user_turns`
- [x] AC-9 (S-04.9): empty turn text → empty list, no exception — verified by `test_s04_9_empty_turn_text`
- [x] AC-10 (S-04.10): malformed JSONL → no unhandled exception, returns list — verified by `test_s04_10_malformed_turn`

All 10 tests pass. Full suite: 83 passed.
