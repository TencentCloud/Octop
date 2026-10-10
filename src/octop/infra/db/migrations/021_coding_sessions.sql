-- Schema v21: coding sessions persistence (S3).
-- 主库（SQLite）。agent_events 跟随主库双方言，不强制 Postgres。
-- coding_runtimes / coding_worktrees / repositories / approval_requests 为
-- S4/S5/S6 预留表：本阶段只建表，不接 repo/业务代码。

CREATE TABLE IF NOT EXISTS coding_sessions (
  session_id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  runner TEXT NOT NULL,
  cwd TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ready',
  turns INTEGER NOT NULL DEFAULT 0,
  acp_session_id TEXT,
  -- S4/S5/S6 预留（全部可空）
  project_id TEXT,
  repository_id TEXT,
  branch TEXT,
  worktree_id TEXT,
  runtime_id TEXT,
  isolation_level TEXT,
  permission_policy TEXT,
  model_profile TEXT,
  trigger TEXT NOT NULL DEFAULT 'interactive',
  token_usage INTEGER NOT NULL DEFAULT 0,
  meta_json TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  closed_at REAL
);

CREATE INDEX IF NOT EXISTS idx_coding_sessions_user
  ON coding_sessions (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_coding_sessions_status
  ON coding_sessions (status);

CREATE TABLE IF NOT EXISTS agent_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL UNIQUE,
  session_id TEXT NOT NULL,
  turn_id TEXT NOT NULL DEFAULT '',
  seq INTEGER NOT NULL,
  ts REAL NOT NULL,
  kind TEXT NOT NULL,
  is_error INTEGER NOT NULL DEFAULT 0,
  payload_json TEXT NOT NULL DEFAULT '{}',
  UNIQUE (session_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_agent_events_session_seq
  ON agent_events (session_id, seq);

-- S4 预留：会话级沙箱运行时
CREATE TABLE IF NOT EXISTS coding_runtimes (
  runtime_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  image TEXT NOT NULL DEFAULT '',
  cpus REAL,
  memory TEXT,
  pids_limit INTEGER,
  allow_network INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'creating',
  container_id TEXT,
  meta_json TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_coding_runtimes_session
  ON coding_runtimes (session_id);

-- S5 预留：git worktree 工作副本
CREATE TABLE IF NOT EXISTS coding_worktrees (
  worktree_id TEXT PRIMARY KEY,
  repository_id TEXT,
  session_id TEXT NOT NULL,
  project_id TEXT,
  branch TEXT NOT NULL DEFAULT '',
  path TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'creating',
  meta_json TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_coding_worktrees_session
  ON coding_worktrees (session_id);

-- S5 预留：仓库元数据
CREATE TABLE IF NOT EXISTS repositories (
  repository_id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  name TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT '',
  provider TEXT NOT NULL DEFAULT '',
  default_branch TEXT NOT NULL DEFAULT 'main',
  meta_json TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_repositories_user
  ON repositories (user_id);

-- S6 预留：HITL 审批持久化（S3 阶段审批决议先落 agent_events）
CREATE TABLE IF NOT EXISTS approval_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id TEXT NOT NULL UNIQUE,
  session_id TEXT NOT NULL,
  turn_id TEXT NOT NULL DEFAULT '',
  tool_name TEXT NOT NULL DEFAULT '',
  tool_kind TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending',
  option_id TEXT,
  decided_by INTEGER,
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL,
  decided_at REAL
);

CREATE INDEX IF NOT EXISTS idx_approval_requests_session
  ON approval_requests (session_id, created_at DESC);

UPDATE _schema_version SET version = 21;
