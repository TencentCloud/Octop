-- Schema v4: sticky per-thread model and reasoning selections.
ALTER TABLE threads ADD COLUMN model_ref TEXT;
ALTER TABLE threads ADD COLUMN reasoning_mode TEXT;
ALTER TABLE threads ADD COLUMN reasoning_effort TEXT;

UPDATE _schema_version SET version = 4;
