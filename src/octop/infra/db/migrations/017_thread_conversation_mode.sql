-- Schema v17: sticky Ask/Plan/Craft mode, pending plan file, and HITL bypass.

ALTER TABLE threads ADD COLUMN conversation_mode TEXT;
ALTER TABLE threads ADD COLUMN pending_plan_path TEXT;
ALTER TABLE threads ADD COLUMN hitl_policy TEXT;

UPDATE _schema_version SET version = 17;
