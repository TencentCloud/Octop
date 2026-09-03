-- Schema v11: cron job display names.

ALTER TABLE cron_jobs ADD COLUMN IF NOT EXISTS name TEXT NOT NULL DEFAULT '';

UPDATE _schema_version SET version = 11;
