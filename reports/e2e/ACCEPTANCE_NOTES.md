# Browser acceptance evidence and correction

Provider for all browser runs: **MOCK**. These tests never supply an API key and do not approve any page as human-reviewed.

- `20260919-235850`: initial run failed because Playwright's string-evaluation wait conflicted with the application's strict CSP. Tests were changed to locator assertions; the CSP was not relaxed. Screenshots, traces and logs are retained.
- `20260920-000051` and `20260920-000437`: four browser-operation tests reported PASS, but their original assertions stopped after execution began. The success fixtures subsequently failed. Inspection exposed Windows path-length-related `FileNotFoundError` in generated JSON temporary paths. **These results are UI-operation evidence only, not successful workflow/compile acceptance.**
- Tests were strengthened: both success workflows must reach `AWAITING_USER_REVIEW`, compile successfully, expose an actual PDF and source ZIP, and render every physical PDF page as a PNG. Beamer output is independently checked for the authorized addition and removal. The failure fixture must now contain `UNDEFINED_CONTROL_SEQUENCE` in its actual compiler report, instead of accepting an arbitrary worker exception.
- Test workspaces use short project-local paths. Existing failed workspaces and evidence are retained. Application temporary-path fixes belong to the backend implementation and are recorded separately.

## Earlier strengthened run

`20260920-001243`: **4 passed, 80 deselected, 2 dependency deprecation warnings; 43.94 seconds.** Run through the shipped `Test-Windows.ps1 -Suite browser` under Windows PowerShell 5.1, using process-only `RemoteSigned` (no saved execution-policy change).

- JUnit: `../test-runs/20260920-001243-011-browser.xml`
- Full log: `../test-runs/20260920-001243-011-browser.log`
- Machine-readable command result: `../test-runs/20260920-001243-011-browser.json`
- Browser screenshots, traces, console records, server/worker logs and test context: `20260920-001243/`
- Preserved runtime and build artifacts: `../../workspace/t/eaf69b98/`

Both success fixtures reached `AWAITING_USER_REVIEW`; no test clicked a human approval button. They produced downloadable PDF and source ZIP files, with every physical page represented by a PNG artifact. The Beamer fixture also verified the actual exported TeX contains the authorized addition and omits the selected example. The failure fixture verified the actual compiler report contains `UNDEFINED_CONTROL_SEQUENCE` and then exercised retry without returning to plan confirmation.

This strengthened run superseded the earlier weak-assertion results for workflow acceptance; earlier evidence remains available for the failure history.

## Latest bounded revalidation

After the PDF geometry and cross-reference changes passed their dedicated checks, `20260920-003847` completed **4 passed, 100 deselected, 2 dependency deprecation warnings; 41.42 seconds**, through the same shipped Windows PowerShell 5.1 runner.

- JUnit / log / command result: `../test-runs/20260920-003846-307-browser.{xml,log,json}`
- Screenshots, traces, console records and service logs: `20260920-003847/`
- Runtime and build artifacts: `../../workspace/t/3f550a70/`
- Temporary service port: `54116`; test services stopped afterward. The final `8765` service was not started by these tests.

The lecture and **actual FDU** Beamer success fixtures again reached `AWAITING_USER_REVIEW`, with PDF, ZIP and all physical-page PNG assertions unchanged. The FDU test additionally verified the visible `theme_adaptations` summary before confirmation and after refresh, and independently checked `\usetheme{fduclassroom}` in the exported source. The unconfigured live-API option and disclosure were checked and captured in `live-unconfigured.png`; the test switched back to MOCK before creating its run. No live request was made. All four console-error records are empty.

The first attempt at this last revalidation was interrupted during collection while the separately developed `math_agent.crossrefs` module had not yet been written (`../test-runs/20260920-003620-699-browser.log`). Browser business tests were NOT_RUN for that attempt. The module's implementation and dedicated regression tests were completed before the final rerun; no new test was deleted or ignored.

Real API acceptance: **NOT_RUN**. Teacher mathematical and visual acceptance: **NOT_RUN**. Clicking and persistence assertions do not substitute for those categories.
