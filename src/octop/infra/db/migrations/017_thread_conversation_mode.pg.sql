-- Schema v17: sticky Ask/Plan/Craft mode and pending plan file per thread.

ALTER TABLE threads ADD COLUMN IF NOT EXISTS conversation_mode TEXT;
ALTER TABLE threads ADD COLUMN IF NOT EXISTS pending_plan_path TEXT;

UPDATE _schema_version SET version = 17;
