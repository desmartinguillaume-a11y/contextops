# BOLT-02: oversized-tool-outputs — Complete

## Summary

Replaced the stub `OversizedToolOutputs.run()` with a full implementation that flags ToolResult entries exceeding per-tool-type token thresholds (2,000 tokens for Bash; 5,000 for all other tools). Wrote a comprehensive 8-test unit test file covering all F-01 acceptance scenarios (S-01.1 through S-01.8).

## Tasks Completed

| # | Task | Status |
|---|------|--------|
| 1 | Implement OversizedToolOutputs.run() | Done |
| 2 | Write unit tests (test_oversized_tool_outputs.py) | Done |

## Commits

- `feat(bolt-02): implement OversizedToolOutputs.run() and add 8 unit tests` — (see hash below)

## Files Created/Modified

- `contextops/auditors/oversized_tool_outputs.py` — Modified: replaced stub `run()` with full implementation including thresholds, evidence, fix_hint, dollar cost, and sorted findings
- `tests/test_oversized_tool_outputs.py` — Created: 8 test functions covering S-01.1 through S-01.8

## Deviations

None. Implementation follows the spec exactly, matching the pattern from `repeated_file_reads.py`.

## Issues Discovered

None.

## Acceptance Criteria

- [x] AC-1 (S-01.1): 9,000-char Bash result → 1 finding with `wasted_tokens==2250`, `auditor=="oversized_tool_outputs"`, `fix_hint` contains "Truncate", `evidence[0]` contains "Bash" and "2,250" — verified by `test_s01_1_bash_exceeds_threshold` (passes)
- [x] AC-2 (S-01.2): 21,000-char Read result → 1 finding with `wasted_tokens==5250`, `fix_hint` contains "offset" or "section" — verified by `test_s01_2_file_read_exceeds_threshold` (passes)
- [x] AC-3 (S-01.3): 9,000-char Bash + 21,000-char Read → 2 findings with `wasted_tokens` 2250 and 5250 — verified by `test_s01_3_both_oversized` (passes)
- [x] AC-4 (S-01.4): 6-char Bash result → `[]` — verified by `test_s01_4_below_threshold` (passes)
- [x] AC-5 (S-01.5): ToolUse with no ToolResult → `[]`, no exception — verified by `test_s01_5_missing_tool_result` (passes)
- [x] AC-6 (S-01.6): ToolResult with null content → `[]`, no exception — verified by `test_s01_6_null_content` (passes)
- [x] AC-7 (S-01.7): Session with only text turns → `[]` — verified by `test_s01_7_no_tool_calls` (passes)
- [x] AC-8 (S-01.8): Malformed ToolUse (no "input" key) → no unhandled exception, returns list — verified by `test_s01_8_malformed_input_key` (passes)

## Test Run Evidence

```
8 passed in 0.03s  (tests/test_oversized_tool_outputs.py)
73 passed in 1.42s (full suite — no regressions)
```
