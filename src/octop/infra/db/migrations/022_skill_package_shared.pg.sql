-- Schema v22: skill packages can be private or shared with other users.

ALTER TABLE skill_packages ADD COLUMN IF NOT EXISTS shared INTEGER NOT NULL DEFAULT 0;

UPDATE _schema_version SET version = 22;
