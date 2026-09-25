-- Schema v18: reversible conversation archiving.

ALTER TABLE threads ADD COLUMN IF NOT EXISTS archived INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_threads_agent_user_archived
  ON threads(agent_id, user_id, archived, pinned, last_active, created_at);

UPDATE _schema_version SET version = 18;
