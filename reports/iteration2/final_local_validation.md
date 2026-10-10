# Iteration 2 local regression record

This report preserves the earlier snapshots. The later chapter-fix complete rerun passed **369 tests**, including 18 selected actual Windows compiler tests, with six deliberately deselected and no failures/skips. See `chapter_fixes_validation.md` and `chapter-final-full-20260920-030902-metadata.json` for the latest full result and unchanged source hashes.

All commands in this record set `MATH_AGENT_LIVE_API_ENABLED=false`, `MATH_AGENT_API_KEY` to an empty process value, and `MATH_AGENT_LLM_STREAMING=false`. They did not import the Windows User API environment, send a model request, or restart the applications on ports 8765/8766. Provider and reviewer behavior in these tests is mock or a synthetic HTTP transport. Real API results belong to separate benchmark reports.

| Validation | Result | Evidence |
| --- | --- | --- |
| Earlier preserved full local snapshot | 210 passed, 6 deselected | `final-local-20260920-020122.log/.xml`, matching metadata JSON |
| Full local suite after global repair, initial legacy recovery and CRLF fixes | 250 passed, 6 deselected, 0 skipped; 133.14 seconds | `final-local-20260920-022414.log/.xml`, `final-local-20260920-022414-metadata.json` |
| Five browser workflows, independent temporary services | 5 passed, 55.40 seconds; all five captured browser console lists empty | `final-ui-20260920-022409-905.log/.xml`, `ui-final-e2e/` |
| Subsequent legacy boundary regression | 68 passed, 26.14 seconds | `legacy_boundaries_final.log/.xml` |
| Final combined differential including answer-number hyperlinks and workflows | 75 passed, 0 skipped, 43.18 seconds | `final-targeted-20260920-023221.log/.xml`, matching metadata JSON |

The 250-test snapshot executed all 14 selected `windows_compile` tests on Windows with the installed XeLaTeX. These cover Chinese paths and overlays, actual cancellation and failed-build diagnostics, forbidden file writes, cross-section references, clean source ZIP compilation, an open PDF during a new revision, equation references and PDF links, captured model fragments under the controlled template, bibliography/CRLF compilation, a broken source table, and mock lecture end-to-end compilation. An actual compiler success is distinct from the mock model responses used to create the content. The metadata records each selected node ID and marker, Python/Windows versions, environment isolation, exact source/test hashes before and after, and no files changed during that full run.

Six tests were deliberately deselected by `-m "not real_api and not e2e"`: five browser tests were run separately and the opt-in real API test was NOT_RUN here. Two dependency deprecation warnings came from Starlette/httpx and AnyIO; neither was a test failure.

After the 250-test and five-browser snapshots completed, targeted legacy fixes enforced zero repair budget at the repair entry point, selected the latest checkpoint, and normalized old unchecked seeds before comparing permitted model edits. The original snapshots are retained and are not relabeled as results from later source hashes. The 68-test differential run exercised these changes and existing draft, fragment, scoped review, actual Windows equation-reference, and CRLF regressions. Overlapping test counts must not be added into a fabricated unique total.

The final 75-test differential also includes the deterministic exercise-number and answer hyperlink renderer fix and complete workflow tests. Actual Windows compilation verifies generated exercise numbers and PDF links. Its metadata records no source/test changes during execution; only `src/math_agent/pipeline.py`, `tests/test_global_repair.py`, and new `tests/test_answer_references.py` differ from the preceding 250-test snapshot. The earlier live smoke PDF was not rebuilt or relabeled by this local validation. No further full-suite or browser rerun is claimed for these final internal changes.

Teacher visual acceptance is NOT_RUN. Rendering pages, verifying links, checking geometry, and automated browser screenshots do not constitute a teacher's mathematical or visual approval. The workflow keeps teaching quality and model limitations visible as NEEDS_REVIEW where applicable.
