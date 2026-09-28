-- Schema v22: who adopted a project comment as the conclusion.
--
-- Canonical v21 -> v22 DDL for PostgreSQL. Executed statement-by-statement by
-- ``_apply_postgresql_migration`` (split on ";\n"), so every statement must be
-- self-contained. ``IF NOT EXISTS`` guards keep a re-run safe; ``migrate.py``
-- gains no ``_ensure_*`` helper for this version.
--
-- Two nullable TEXT columns on ``project_comments``; NULL means "not the
-- conclusion" or "adopted before this column existed".
--
-- Timestamp-free by design: the mark's own lifetime is the comment row's.

ALTER TABLE project_comments ADD COLUMN IF NOT EXISTS concluded_by_type TEXT;

ALTER TABLE project_comments ADD COLUMN IF NOT EXISTS concluded_by_id TEXT;

UPDATE _schema_version SET version = 22;
