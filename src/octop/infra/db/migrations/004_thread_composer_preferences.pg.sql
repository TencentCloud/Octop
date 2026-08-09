-- Schema v4: sticky per-thread model and reasoning selections.
ALTER TABLE threads ADD COLUMN IF NOT EXISTS model_ref TEXT;
ALTER TABLE threads ADD COLUMN IF NOT EXISTS reasoning_mode TEXT;
ALTER TABLE threads ADD COLUMN IF NOT EXISTS reasoning_effort TEXT;

UPDATE _schema_version SET version = 4;
