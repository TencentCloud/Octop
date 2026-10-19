-- Schema v21: skill packages can disable ZIP download for non-owners.

ALTER TABLE skill_packages ADD COLUMN IF NOT EXISTS allow_download INTEGER NOT NULL DEFAULT 1;

UPDATE _schema_version SET version = 21;
