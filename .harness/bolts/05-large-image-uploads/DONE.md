# BOLT-05: large-image-uploads — Complete

## Summary

Replaced the stub `LargeImageUploads.run()` body with a full single-pass implementation
that detects oversized base64 image blocks (>50,000 chars) and cross-turn duplicate images
by reading `turn.raw` directly (bypassing the typed content layer which discards image blocks).
Nine unit tests covering all F-03 acceptance scenarios were written and are passing.

## Tasks Completed

| # | Task | Status |
|---|------|--------|
| 1 | Implement LargeImageUploads.run() | Done |
| 2 | Write unit tests (9 F-03 scenarios) | Done |

## Commits

- `feat(bolt-05): implement LargeImageUploads auditor and unit tests`

## Files Created/Modified

- `contextops/auditors/large_image_uploads.py` — Modified: replaced stub with full implementation using hashlib.md5 for dedup, single-pass oversized detection, sorted findings by wasted_tokens descending
- `tests/test_large_image_uploads.py` — Created: 9 test functions covering S-03.1 through S-03.9

## Deviations

- The bolt spec references `turn.turn_index` but the actual `Turn` dataclass field is `turn.index`. The implementation uses `turn.index` consistently (matching the real field name). The `turn_index` naming in the spec is documentation convention only.
- Test S-03.1 uses a 3rd user turn (index 2) to satisfy "evidence references turn 2" as specified.

## Issues Discovered

None.

## Acceptance Criteria

- [x] AC-1 (S-03.1): 60,000-char base64 → 1 Finding with auditor=="large_image_uploads", wasted_tokens==15000, wasted_dollars>0, fix_hint contains "Resize"/"Files API", evidence[0] references turn 2. Verified by `test_s03_1_single_large_image`.
- [x] AC-2 (S-03.2): Same 55,000-char base64 in two turns → ≥2 findings; duplicate fix_hint references "2". Verified by `test_s03_2_same_large_image_two_turns`.
- [x] AC-3 (S-03.3): 300-char base64 → []. Verified by `test_s03_3_image_below_threshold`.
- [x] AC-4 (S-03.4): source.type=="url", no data field → [], no exception. Verified by `test_s03_4_url_source_type_skipped`.
- [x] AC-5 (S-03.5): message.content is string → [], no exception. Verified by `test_s03_5_content_is_string_not_list`.
- [x] AC-6 (S-03.6): image block missing "source" key → [], no exception. Verified by `test_s03_6_image_block_missing_source_key`.
- [x] AC-7 (S-03.7): Only text blocks → []. Verified by `test_s03_7_no_image_blocks`.
- [x] AC-8 (S-03.8): Two distinct 60,000-char images in one turn → exactly 2 findings. Verified by `test_s03_8_multiple_different_large_images_same_turn`.
- [x] AC-9 (S-03.9): source.data is integer 42 → [], no exception. Verified by `test_s03_9_data_field_is_integer`.
