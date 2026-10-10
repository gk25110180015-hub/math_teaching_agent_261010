# Final chapter-fix regression snapshot and follow-up

**Latest complete rerun: 369 passed, zero failures, zero skipped, six deliberately deselected, 178.15 seconds.** This rerun occurred after the Store and provider fixes described below. All 18 selected actual Windows compiler tests executed; source/test/pyproject/lockfile hashes were unchanged during the run. See `chapter-final-full-20260920-030902.log/.xml/-metadata.json` and `chapter_final_full_summary.json`. Two existing dependency deprecation warnings remain. No further test reruns were performed after this successful result.

The earlier full local regression after actual CH01/CH02/CH03 fixes completed with **360 passed, one failed, six deselected** in 179.71 seconds. The failure was the SQLite concurrent-initialization race, subsequently fixed and verified by targeted tests and the final complete rerun. It is incorrect to describe that original full run as all passing.

The full command used `-m "not real_api and not e2e"`, an independent short workspace, empty API key, live API disabled and streaming disabled. All 18 selected `windows_compile` tests executed. The full snapshot contains the label-recovery, missing-answer, reviewer/rendering contract and Chinese-punctuation changes. Its before/after hashes show no product-source change during execution; only `tests/test_answer_recovery_pipeline.py` received its fourth test after collection. That file was then explicitly retested.

| Run | Recorded result | Evidence |
| --- | --- | --- |
| Earlier complete local snapshot | 360 passed, 1 failed, 6 deselected; 179.71 s | `chapter-fixes-full-20260920-025628.log/.xml/-metadata.json` |
| Store, state, answers and reviewer scope after the lock fix | 77 passed; 17.59 s | `migration_concurrency_final.log/.xml` |
| Additional rollback fixture, state/API/actor/policy and Windows workflows | 27 passed; 16.02 s | `migration_state_integration.log/.xml` |
| Provider JSON diagnostic-feedback patch, independently executed by root | 34 passed, 1 real-API test deselected; 0.85 s | `provider-repair-feedback.log/.xml` |
| Final complete rerun after all fixes | 369 passed, 0 failures, 0 skipped, 6 deselected; 178.15 s | `chapter-final-full-20260920-030902.log/.xml/-metadata.json` |

The provider patch followed actual invalid JSON caused by incorrectly escaped TeX backslashes. Tests verify safe error position/context feedback, the compatible protocol, streaming and failure archives. The running real driver had already imported the previous provider implementation: its subsequent success does not constitute live validation of the new feedback. Original malformed responses were preserved by the previously installed archive feature.

The original full-run failure, deterministic red test and an additional three-test Windows temporary-path failure are all retained. The latter passed after choosing a shorter isolated test path; it was not silently removed from the record. Detailed evidence is in `migration_concurrency_validation.md`.

`chapter_fixes_final_snapshot.json` retains the historical first full-run/follow-up snapshot, while `chapter_final_full_summary.json` records the later successful complete rerun and its evidence hashes. Neither replaces the original failed result. Overlapping targeted test counts must not be summed into a fabricated unique total. The five earlier browser E2E cases were not repeated for these internal changes; their earlier snapshot remains separate.

All model calls in these local tests are mocks or synthetic transports; **real API testing is NOT_RUN in this record**. Windows XeLaTeX and multi-process SQLite tests are actual local execution. Teacher mathematical/visual acceptance remains **NOT_RUN**. Real chapter generation results must be read from the independently running benchmark reports.
