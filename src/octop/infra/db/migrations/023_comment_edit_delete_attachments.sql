-- Schema v23: comment attachments (which comment an uploaded file belongs to).
--
-- Canonical v22 -> v23 DDL for SQLite. ``project_artifacts`` already stores the
-- project's files; this nullable column records the comment that introduced one,
-- so a deleted comment can take its own attachments with it.
--
-- Additive column only -- no table rebuild, no ``migrate.py`` helper (same
-- precedent as 022_project_comment_concluded_by.sql).

ALTER TABLE project_artifacts ADD COLUMN comment_id TEXT;

UPDATE _schema_version SET version = 23;
