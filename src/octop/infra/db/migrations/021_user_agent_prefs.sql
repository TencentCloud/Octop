-- Schema v21: per-user agent ordering + pinning (sidebar list order, cross-device).

CREATE TABLE IF NOT EXISTS user_agent_prefs (
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  agent_id   TEXT    NOT NULL,
  pinned     INTEGER NOT NULL DEFAULT 0,
  sort_order INTEGER NOT NULL DEFAULT -1,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (user_id, agent_id)
);

CREATE INDEX IF NOT EXISTS idx_uap_user_order ON user_agent_prefs(user_id, sort_order);

UPDATE _schema_version SET version = 21;
