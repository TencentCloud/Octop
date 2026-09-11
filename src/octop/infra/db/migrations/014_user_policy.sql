-- Schema v14: per-user policies (resource rows; missing/disabled = default).
-- Expert composer defaults (knowledge_base_ids, mcp_servers) are added by
-- migrate.py::_ensure_agent_profile_columns because this file is not executed
-- on SQLite (version 14 uses the Python helper instead).

CREATE TABLE user_policies (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  policy_id  TEXT    NOT NULL UNIQUE,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name       TEXT    NOT NULL,
  enabled    INTEGER NOT NULL DEFAULT 1,
  value      TEXT    NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE(user_id, name)
);

UPDATE _schema_version SET version = 14;
