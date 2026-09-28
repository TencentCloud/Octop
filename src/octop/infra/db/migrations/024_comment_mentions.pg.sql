-- Schema v24: structured mentions on a comment.
--
-- Canonical v23 -> v24 DDL for PostgreSQL. Executed statement-by-statement by
-- ``_apply_postgresql_migration`` (split on ";\n"), so every statement must be
-- self-contained. ``IF NOT EXISTS`` keeps a re-run safe; ``migrate.py`` gains no
-- ``_ensure_*`` helper for this version.
--
-- The value is a JSON array of ``{type,id}`` objects exactly as submitted by the
-- dashboard; the server neither validates nor rewrites its contents here.
--
-- NULL means "this comment mentions nobody".

ALTER TABLE project_comments ADD COLUMN IF NOT EXISTS mentions TEXT;

UPDATE _schema_version SET version = 24;
