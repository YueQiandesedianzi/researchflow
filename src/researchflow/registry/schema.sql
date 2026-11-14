-- ResearchFlow Registry schema v1（只增不改；runs.status 仅允许运行期状态推进）
CREATE TABLE IF NOT EXISTS schema_migrations (
  version     INTEGER PRIMARY KEY,
  applied_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
  run_id        TEXT PRIMARY KEY,
  seq           INTEGER UNIQUE,
  node_id       TEXT NOT NULL,
  block_id      TEXT NOT NULL,
  block_version TEXT NOT NULL,
  status        TEXT NOT NULL,          -- running/completed/validated/failed/failed_validation/interrupted
  cache_key     TEXT,
  started_at    TEXT,
  finished_at   TEXT,
  run_json      TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_runs_node ON runs(node_id);
CREATE INDEX IF NOT EXISTS idx_runs_cache ON runs(cache_key);

CREATE TABLE IF NOT EXISTS artifacts (
  id      INTEGER PRIMARY KEY,
  run_id  TEXT NOT NULL REFERENCES runs(run_id),
  port    TEXT NOT NULL,
  path    TEXT NOT NULL,                -- 项目相对路径（POSIX）
  sha256  TEXT NOT NULL,
  type    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artifacts_run ON artifacts(run_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_hash ON artifacts(sha256);

CREATE TABLE IF NOT EXISTS metrics (
  run_id  TEXT NOT NULL REFERENCES runs(run_id),
  name    TEXT NOT NULL,
  value   REAL NOT NULL,
  PRIMARY KEY (run_id, name)
);

CREATE TABLE IF NOT EXISTS validations (
  id      INTEGER PRIMARY KEY,
  run_id  TEXT NOT NULL REFERENCES runs(run_id),
  name    TEXT NOT NULL,
  passed  INTEGER NOT NULL,
  detail  TEXT
);

CREATE TABLE IF NOT EXISTS decisions (
  id           INTEGER PRIMARY KEY,
  node_id      TEXT NOT NULL,
  mode         TEXT NOT NULL,           -- auto / manual / auto_then_manual
  expression   TEXT,
  auto_result  INTEGER,                 -- 自动判据建议（可空）
  final_result INTEGER NOT NULL,        -- 1 pass / 0 fail
  actor        TEXT NOT NULL,           -- auto | human:<name>
  comment      TEXT,
  decided_at   TEXT NOT NULL,
  evidence     TEXT                     -- 决策依据指纹 JSON（上游 Run/产物摘要 + 判据）
);
CREATE INDEX IF NOT EXISTS idx_decisions_node ON decisions(node_id);

CREATE TABLE IF NOT EXISTS exports (
  id         INTEGER PRIMARY KEY,
  out_dir    TEXT NOT NULL,
  nodes      TEXT NOT NULL,             -- JSON 数组
  verified   INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
