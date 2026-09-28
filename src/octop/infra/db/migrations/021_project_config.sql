-- Schema v21: project configuration (connector kinds, skill projections, instruction,
-- cron ownership).
--
-- Canonical v20 -> v21 DDL. Applied by ``run_migrations``' generic SQL path
-- (``executescript``) -- ``migrate.py`` deliberately gains no ``_ensure_*`` helper
-- for this version, so the two ``if version == N:`` branches stay put.
--
-- Exactly the seven DDL items frozen in PLAN.md §10.1: two declaration tables
-- (each with its read-path index), two columns, and one index for the cron list
-- path. ``project_connectors`` stores the connector **kind only** -- never an
-- instance id or credential (R17).
--
-- Timestamp columns are INTEGER unix seconds, matching 001_initial.

CREATE TABLE IF NOT EXISTS project_connectors (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  kind       TEXT NOT NULL,
  created_by INTEGER NOT NULL REFERENCES users(id),
  created_at INTEGER NOT NULL,
  UNIQUE(project_id, kind)
);
CREATE INDEX IF NOT EXISTS idx_project_connectors_project ON project_connectors(project_id, kind);

CREATE TABLE IF NOT EXISTS project_skills (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  agent_id   TEXT NOT NULL,
  skill_slug TEXT NOT NULL,
  created_by INTEGER NOT NULL REFERENCES users(id),
  created_at INTEGER NOT NULL,
  UNIQUE(project_id, agent_id, skill_slug)
);
CREATE INDEX IF NOT EXISTS idx_project_skills_project ON project_skills(project_id, agent_id);

ALTER TABLE projects ADD COLUMN instruction TEXT NOT NULL DEFAULT '';

ALTER TABLE cron_jobs ADD COLUMN project_id TEXT;
CREATE INDEX IF NOT EXISTS idx_cron_jobs_project ON cron_jobs(project_id);

UPDATE _schema_version SET version = 21;
