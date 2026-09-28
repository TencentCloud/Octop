-- Schema v22: who adopted a project comment as the conclusion.
--
-- Canonical v21 -> v22 DDL for SQLite. Two nullable columns on
-- ``project_comments`` record the adopting actor, so the conclusion marker keeps
-- its actor for the whole lifetime of the mark (PLAN.md §2.1c): a comment that is
-- not the conclusion leaves both columns NULL.
--
-- Additive columns only -- no table rebuild, no ``migrate.py`` helper (same
-- precedent as 021_project_config.sql).

ALTER TABLE project_comments ADD COLUMN concluded_by_type TEXT;

ALTER TABLE project_comments ADD COLUMN concluded_by_id TEXT;

UPDATE _schema_version SET version = 22;
