-- Schema v17: sticky Ask/Plan/Craft mode, pending plan file, and HITL bypass.

ALTER TABLE threads ADD COLUMN IF NOT EXISTS conversation_mode TEXT;
ALTER TABLE threads ADD COLUMN IF NOT EXISTS pending_plan_path TEXT;
ALTER TABLE threads ADD COLUMN IF NOT EXISTS hitl_policy TEXT;

UPDATE _schema_version SET version = 17;
