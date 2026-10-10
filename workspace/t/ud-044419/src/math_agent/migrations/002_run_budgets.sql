CREATE TABLE IF NOT EXISTS run_budgets (
 run_id TEXT PRIMARY KEY REFERENCES runs(id), version INTEGER NOT NULL DEFAULT 0,
 defaults_json TEXT NOT NULL, overrides_json TEXT NOT NULL, source TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS budget_actions (
 run_id TEXT NOT NULL REFERENCES runs(id), action_id TEXT NOT NULL, payload_hash TEXT NOT NULL,
 before_json TEXT NOT NULL, after_json TEXT NOT NULL, actor TEXT NOT NULL, note TEXT NOT NULL,
 created_at TEXT NOT NULL, PRIMARY KEY(run_id,action_id)
);
