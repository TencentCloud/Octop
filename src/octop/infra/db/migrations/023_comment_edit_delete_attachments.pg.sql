-- Schema v23: comment attachments (which comment an uploaded file belongs to).
--
-- Canonical v22 -> v23 DDL for PostgreSQL. Executed statement-by-statement by
-- ``_apply_postgresql_migration`` (split on ";\n"), so every statement must be
-- self-contained. ``IF NOT EXISTS`` keeps a re-run safe; ``migrate.py`` gains no
-- ``_ensure_*`` helper for this version.
--
-- NULL means "a project file that is not attached to a comment", which is what
-- every pre-v23 row becomes.

ALTER TABLE project_artifacts ADD COLUMN IF NOT EXISTS comment_id TEXT;

UPDATE _schema_version SET version = 23;
