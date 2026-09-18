-- Schema v16: thread organization (folder + tags).

ALTER TABLE threads ADD COLUMN folder TEXT;
ALTER TABLE threads ADD COLUMN tags TEXT NOT NULL DEFAULT '[]';

CREATE INDEX idx_threads_folder ON threads(agent_id, user_id, folder);

UPDATE _schema_version SET version = 16;
