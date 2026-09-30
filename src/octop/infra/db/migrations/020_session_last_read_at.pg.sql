-- Schema v20: sessions.last_read_at — kanban Done clears after the user opens the chat.

ALTER TABLE sessions ADD COLUMN IF NOT EXISTS last_read_at INTEGER NOT NULL DEFAULT 0;

UPDATE sessions SET last_read_at = updated_at WHERE last_read_at = 0 AND updated_at > 0;

UPDATE _schema_version SET version = 20;
