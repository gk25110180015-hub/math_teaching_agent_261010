# Global review recovery and Windows source bytes

This change responds to the preserved live smoke failure in run `426866cf71d2437bb17b54ac801a8c18`: global review identified an unstated integer-unboundedness/Archimedean premise in S01.U05 and S01.U07 after local review. Previously a retry could reuse unchanged checked sections and fail again, or reroll the review without carrying the recorded concern forward.

The pipeline now groups actual reported unit IDs by section, calls the existing repair role with only those IDs authorized, and requires the same section ID, unit IDs/order, exact non-target units, non-target calculations, and unrelated uncertainty metadata. Raw, normalized, before/after candidates and every repair-state revision remain on disk. All affected and following sections undergo normalization, local content/reference/math/model checks and compilation again; all adjacent interfaces are then reviewed. The plan approval remains unchanged and no teacher approval is created. A persisted global round budget uses `max_local_repair_attempts`; exhausted retries cannot silently restart it within the same repair identity.

Unchecked repaired candidates have controlled paths and SHA-256 validation. Resume after a following-section review timeout reuses those bodies and repeats their checks instead of reauthoring. The checked-cache version is `writer-v4-labeled-eq-global-repair` so the equation-label and repair checks invalidate older checked results.

Legacy `global_review_failure.json` is imported before any new global review. The importer validates actual unit IDs, available review body hashes, checkpoint JSON hashes, and exact source-file hashes. Existing checked-section bodies are reused only as unchecked repair seeds, including when the old checked-cache version differs. Old reports lacking body hashes explicitly record this limitation; the concern is conservatively retained. An unverified or corrupt linkage blocks recovery instead of dropping the concern. New failure reports contain plan and unit hashes.

Both local and final lecture TeX writes now encode exact UTF-8 bytes. A CRLF-containing render previously became CRCRLF on Windows; two regression fixtures reproduce that failure and verify exact source-byte preservation. These tests use fake providers and compilation and do not establish API or compiler acceptance.

Evidence:

- `global_repair_red.log`: original red tests before global repair implementation.
- `global_repair_targeted.log` / `.xml`: 81 passed in 70.97 seconds, including existing real Windows compilation tests; provider operations were mock/fake and live API explicitly disabled.
- `crlf_legacy_red.log`: all five initial CRLF/legacy fixtures failed before their corresponding fixes.
- `crlf_legacy_final.log` / `.xml`: 24 passed in 9.48 seconds, targeted global-repair, draft recovery and CRLF fixtures.
- `legacy_boundaries_red.log`: the zero-budget and older non-target labeled-equation recovery fixtures both initially failed. The labeled-equation fixture also exposed selection of an arbitrary older checkpoint when multiple cache versions existed.
- `legacy_boundaries_final.log` / `.xml`: 68 passed in 26.14 seconds after enforcing the round budget at the sole repair-start entry point, choosing the latest preserved checkpoint, and retaining raw/canonical seed normalization evidence before scoped model repair. Includes actual Windows equation-reference and CRLF compilation checks; all provider activity remains synthetic/offline.
- `final-targeted-20260920-023221.log` / `.xml`: final combined 75 passed in 43.18 seconds, also covering exercise answer links and workflows. Metadata confirms no source/test changes during this run.

These are engineering regression results. Real model calls were NOT_RUN in this validation. Teacher visual acceptance remains NOT_RUN. Model review is not a general mathematical proof, and a remaining `review` or `blocking` issue still prevents completion.
