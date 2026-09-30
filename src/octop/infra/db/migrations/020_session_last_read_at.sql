-- Schema v20: sessions.last_read_at — kanban Done clears after the user opens the chat.

ALTER TABLE sessions ADD COLUMN last_read_at INTEGER NOT NULL DEFAULT 0;

-- Existing rows start as already viewed at last touch so upgrade does not
-- dump every historical assistant reply into Done.
UPDATE sessions SET last_read_at = updated_at WHERE last_read_at = 0 AND updated_at > 0;

UPDATE _schema_version SET version = 20;
