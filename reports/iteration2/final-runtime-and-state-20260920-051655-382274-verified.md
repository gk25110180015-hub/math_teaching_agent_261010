# Final read-only runtime and state snapshot

UTC: 2026-09-19T21:16:55.382274+00:00

Snapshot checks: **PASS_SNAPSHOT**. No API model calls, service stop/start, budget increase, database or source edits. SQLite opened with mode=ro; HTTP requests were GET health/capabilities only.

| Port | Health | Worker alive | Key configured | Model | Streaming |
|---|---|---|---|---|---|
| 8765 | PASS | True | True | gpt-6-astra | True |
| 8766 | PASS | True | True | gpt-6-astra | True |

Provider settings and workspace heartbeat evidence are recorded in the JSON; only the configured boolean is recorded for credentials.

| Case | Status / stage | Requests | Effective requests/local/global | Budget version/actions | Teacher reviews |
|---|---|---|---|---|---|
| smoke | AWAITING_USER_REVIEW / review.pages_and_quality | 21 | 60/UNRECORDED/UNRECORDED | 0/0 | 0 |
| CH01 | AWAITING_USER_REVIEW / review.pages_and_quality | 37 | 60/2/2 | 0/0 | 0 |
| CH02 | BLOCKED / review.section.S04 | 33 | 60/2/2 | 0/0 | 0 |
| CH03 | BLOCKED / review.section.S03 | 27 | 60/2/2 | 0/0 | 0 |

Total benchmark requests: **118**, expected 118. No existing requests were reset or hidden. All four persisted budgets have no increases only if `no_budget_increase` is true in the JSON.

Original materials: **PASS**, 53 files rehashed against the preserved manifest. Full paths and expected/observed SHA256 are in `final-originals-20260920-051655-382274.json`.

These are runtime/state/integrity checks, not new model or compilation acceptance. The smoke run still requires user review; blocked chapter runs are not finished teaching deliverables. Teacher visual acceptance is NOT_RUN for all four runs. Native trusted_local compilation is not an isolation sandbox.

Full machine-readable evidence: `final-runtime-and-state-20260920-051655-382274-verified.json`.

Addendum: job statuses were checked using their actual lowercase storage form; both workspaces have zero queued/running jobs. The smoke budget row records requests=60 only. Its local/global repair ceilings are explicitly UNRECORDED here; current defaults were neither inferred as historical values nor written to the database. The other three runs persist 60/2/2.
