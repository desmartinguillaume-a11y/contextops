# BOLT-03: duplicate-bash-runs — Complete

## Summary

Replaced the stub `DuplicateBashRuns.run()` body with a full implementation that detects normalized bash commands repeated 2 or more times with no intervening state-mutating command, and created a comprehensive 9-scenario unit test file covering all F-02 acceptance criteria. The implementation follows the same structural pattern as `repeated_file_reads.py`, using a per-command occurrence list and a `blocked` set that is globally reset whenever any mutation command is encountered.

## Tasks Completed

| # | Task | Status |
|---|------|--------|
| 1 | Implement DuplicateBashRuns.run() | Done |
| 2 | Write unit tests (tests/test_duplicate_bash_runs.py) | Done |

## Commits

- `feat(bolt-03): implement DuplicateBashRuns auditor with 9 unit tests`

## Files Created/Modified

- `contextops/auditors/duplicate_bash_runs.py` — Modified: replaced stub with full implementation including `MUTATION_MARKERS`, `_normalize()`, `_is_mutation()` helpers, and complete `run()` logic
- `tests/test_duplicate_bash_runs.py` — Created: 9 test functions covering all F-02 scenarios S-02.1 through S-02.9

## Deviations

None. Implementation follows the spec exactly, including the global mutation-reset logic described in the Notes section.

## Issues Discovered

None.

## Acceptance Criteria

- [x] AC-1 (S-02.1): Two "git status" calls, no mutation → 1 Finding with auditor=="duplicate_bash_runs", len(evidence)==2, fix_hint contains "Cache" — verified by `test_s02_1_same_command_twice_no_mutation`
- [x] AC-2 (S-02.2): "git status", "git commit -m 'fix'", "git status" → [] — verified by `test_s02_2_same_command_mutation_in_between`
- [x] AC-3 (S-02.3): "git  status" (double space) and "git status" treated as equal → 1 Finding referencing both calls — verified by `test_s02_3_whitespace_normalization`
- [x] AC-4 (S-02.4): "git status"×2 + "ls -la"×2 → 2 Findings — verified by `test_s02_4_two_distinct_commands_each_repeated`
- [x] AC-5 (S-02.5): "cat pyproject.toml"×4 → 1 Finding with len(evidence)==4 — verified by `test_s02_5_four_repeats_one_finding`
- [x] AC-6 (S-02.6): Only Read/Glob calls → [] — verified by `test_s02_6_no_bash_calls`
- [x] AC-7 (S-02.7): Three unique commands → [] — verified by `test_s02_7_all_unique_commands`
- [x] AC-8 (S-02.8): Bash ToolUse with no "command" key → no exception, skipped gracefully — verified by `test_s02_8_malformed_no_command_key`
- [x] AC-9 (S-02.9): Empty session → [] — verified by `test_s02_9_zero_turns`

All 9 tests pass. Full suite: 73 passed, 0 failed.
