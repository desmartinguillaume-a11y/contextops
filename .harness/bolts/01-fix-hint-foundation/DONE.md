# BOLT-01: fix-hint-foundation — Complete

## Summary

Added the `fix_hint: str | None = None` field to the `Finding` dataclass as the last field after `evidence`, maintaining full backward compatibility. Created four minimal stub auditor modules (`oversized_tool_outputs`, `duplicate_bash_runs`, `large_image_uploads`, `prompt_context_stuffing`) and registered them in `all_auditors()`, growing the registry from 6 to 10 auditors. A new unit test file covers all four ACs.

## Tasks Completed

| # | Task | Status |
|---|------|--------|
| 1 | Add fix_hint field to Finding dataclass | Done |
| 2 | Create four stub auditor modules | Done |
| 3 | Register new auditors in all_auditors() | Done |

## Commits

- `feat(bolt-01): add fix_hint field to Finding, stub four new auditors` — (see git log)

## Files Created/Modified

- `contextops/auditors/__init__.py` — Modified: added `fix_hint: str | None = None` to `Finding`; added 4 lazy imports and instantiations in `all_auditors()`
- `contextops/auditors/oversized_tool_outputs.py` — Created: stub auditor, category RIGHTSIZING
- `contextops/auditors/duplicate_bash_runs.py` — Created: stub auditor, category ZOMBIE
- `contextops/auditors/large_image_uploads.py` — Created: stub auditor, category RIGHTSIZING
- `contextops/auditors/prompt_context_stuffing.py` — Created: stub auditor, category OVERPROVISIONING
- `tests/test_finding_fix_hint.py` — Created: 4 unit tests covering AC-1 through AC-4

## Deviations

None. Implementation follows the spec exactly.

## Issues Discovered

None.

## Acceptance Criteria

- [x] AC-1: `Finding` constructed without `fix_hint` succeeds and `finding.fix_hint is None` — verified by `test_finding_no_fix_hint_defaults_to_none` passing
- [x] AC-2: `Finding(..., fix_hint="Truncate bash output to the first 50 lines.")` sets the value — verified by `test_finding_with_fix_hint` passing
- [x] AC-3: `all_auditors()` returns list of length 10 with all expected `name` attributes — verified by `test_all_auditors_length_and_names` passing
- [x] AC-4: All 10 auditors pass `isinstance(auditor, Auditor)` with non-empty name/title/category and callable run — verified by `test_all_auditors_are_auditor_instances` passing
- [x] AC-5: All 56 tests pass (52 pre-existing + 4 new) with exit code 0 — verified by `.venv/bin/pytest tests/ -q` output: `56 passed in 1.33s`
- [x] AC-6: `python -c "import contextops.auditors.oversized_tool_outputs, ..."` exits with code 0 — verified directly
