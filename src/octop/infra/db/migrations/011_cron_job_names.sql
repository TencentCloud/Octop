-- Schema v11: cron job display names.
-- SQLite applies this via migrate.py::_ensure_cron_jobs_schema so the upgrade
-- remains idempotent for databases repaired ahead of the version watermark.

ALTER TABLE cron_jobs ADD COLUMN name TEXT NOT NULL DEFAULT '';

UPDATE _schema_version SET version = 11;
