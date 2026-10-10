CREATE TABLE IF NOT EXISTS runs (
 id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
 owner_id TEXT NOT NULL DEFAULT 'local', status TEXT NOT NULL, stage TEXT NOT NULL,
 input_json TEXT NOT NULL, input_hash TEXT NOT NULL, active_plan_revision INTEGER,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, error_json TEXT,
 request_count INTEGER NOT NULL DEFAULT 0, schema_version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS plans (
 run_id TEXT NOT NULL REFERENCES runs(id), revision INTEGER NOT NULL, hash TEXT NOT NULL,
 canonical_json TEXT NOT NULL, parent_revision INTEGER, status TEXT NOT NULL,
 created_at TEXT NOT NULL, PRIMARY KEY(run_id,revision)
);
CREATE TABLE IF NOT EXISTS decisions (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), question_id TEXT,
 question_revision INTEGER, payload_json TEXT NOT NULL, actor TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
 run_id TEXT NOT NULL REFERENCES runs(id), revision INTEGER NOT NULL, hash TEXT NOT NULL,
 input_hash TEXT NOT NULL, action_id TEXT NOT NULL, confirmed_at TEXT NOT NULL,
 PRIMARY KEY(run_id,revision)
);
CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), kind TEXT NOT NULL,
 build_key TEXT NOT NULL UNIQUE, status TEXT NOT NULL, lease_owner TEXT,
 lease_deadline REAL, fencing_token INTEGER NOT NULL DEFAULT 0, attempt INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, error_json TEXT
);
CREATE TABLE IF NOT EXISTS steps (
 run_id TEXT NOT NULL REFERENCES runs(id), step_key TEXT NOT NULL, input_hash TEXT NOT NULL,
 output_json TEXT NOT NULL, output_hash TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(run_id,step_key,input_hash)
);
CREATE TABLE IF NOT EXISTS events (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(id),
 type TEXT NOT NULL, payload_json TEXT NOT NULL, timestamp TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS artifacts (
 artifact_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), revision INTEGER NOT NULL,
 storage_key TEXT NOT NULL, name TEXT NOT NULL, sha256 TEXT NOT NULL, media_type TEXT NOT NULL,
 status TEXT NOT NULL, metadata_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
 run_id TEXT NOT NULL REFERENCES runs(id), artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
 sha256 TEXT NOT NULL, verdict TEXT NOT NULL, note TEXT NOT NULL, actor TEXT NOT NULL,
 created_at TEXT NOT NULL, PRIMARY KEY(run_id,artifact_id,sha256)
);
CREATE TABLE IF NOT EXISTS worker_heartbeats (id TEXT PRIMARY KEY, timestamp REAL NOT NULL);
