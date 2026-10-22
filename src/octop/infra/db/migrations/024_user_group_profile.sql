-- Schema v24: user groups can be disabled and can carry a preset avatar;
-- knowledge bases and bridge connections gain an optional uploaded/remote icon_url;
-- bridge connections gain shared (who can use the link).
-- SQLite applies this through _ensure_user_group_profile_schema /
-- _ensure_knowledge_base_icon_url_schema / _ensure_bridge_icon_url_schema /
-- _ensure_bridge_shared_schema so a replay onto a database that already has the
-- columns does not fail.

ALTER TABLE user_group ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1;
ALTER TABLE user_group ADD COLUMN avatar_icon TEXT;
ALTER TABLE knowledge_bases ADD COLUMN icon_url TEXT NOT NULL DEFAULT '';
ALTER TABLE bridge_connections ADD COLUMN icon_url TEXT NOT NULL DEFAULT '';
ALTER TABLE bridge_connections ADD COLUMN shared INTEGER NOT NULL DEFAULT 0;

-- OpenDesign task tracking.
CREATE TABLE IF NOT EXISTS open_design_tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT NOT NULL UNIQUE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  instance_id TEXT NOT NULL,
  agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
  thread_id TEXT NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
  project TEXT NOT NULL,
  request_id TEXT NOT NULL,
  run_id TEXT,
  status TEXT NOT NULL DEFAULT 'submitting',
  result_json TEXT NOT NULL DEFAULT '{}',
  last_error TEXT,
  failures INTEGER NOT NULL DEFAULT 0,
  next_check INTEGER NOT NULL DEFAULT 0,
  revision INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE(user_id, instance_id, agent_id, thread_id, request_id)
);
CREATE INDEX IF NOT EXISTS idx_open_design_tasks_thread ON open_design_tasks(user_id, agent_id, thread_id, created_at);
CREATE INDEX IF NOT EXISTS idx_open_design_tasks_due ON open_design_tasks(next_check, status);

UPDATE _schema_version SET version = 24;
