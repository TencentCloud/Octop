-- Schema v20: project task metadata (tags, custom fields, start date, attachment metadata).
--
-- Canonical v19 -> v20 DDL. Applied by ``run_migrations``' generic SQL path
-- (``executescript``) -- ``migrate.py`` deliberately gains no ``_ensure_*``
-- helper for this version, so the two ``if version == N:`` branches stay put.
--
-- The DDL budget is PLAN.md §12.1's nine items plus the two custom-field indexes
-- frozen by §6.1 (11 statements in total): one task column, two tag tables (+
-- their indexes), two custom-field tables (+ their indexes), and two columns on
-- ``project_artifacts``. No ``default`` column on the custom-field table (S-9).
--
-- Timestamp columns are INTEGER unix seconds, matching 001_initial.

ALTER TABLE project_tasks ADD COLUMN start_at INTEGER;

CREATE TABLE IF NOT EXISTS project_tags (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  tag_id     TEXT NOT NULL UNIQUE,
  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  name       TEXT NOT NULL,
  color      TEXT NOT NULL DEFAULT '',
  created_by INTEGER NOT NULL REFERENCES users(id),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE(project_id, name)
);
CREATE INDEX IF NOT EXISTS idx_project_tags_project ON project_tags(project_id, name);

CREATE TABLE IF NOT EXISTS project_task_tags (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id    TEXT NOT NULL REFERENCES project_tasks(task_id) ON DELETE CASCADE,
  tag_id     TEXT NOT NULL REFERENCES project_tags(tag_id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL,
  UNIQUE(task_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_project_task_tags_tag ON project_task_tags(tag_id);

CREATE TABLE IF NOT EXISTS project_custom_fields (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  field_id   TEXT NOT NULL UNIQUE,
  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  key        TEXT NOT NULL,
  label      TEXT NOT NULL,
  type       TEXT NOT NULL,
  required   INTEGER NOT NULL DEFAULT 0,
  options    TEXT NOT NULL DEFAULT '[]',
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_by INTEGER NOT NULL REFERENCES users(id),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE(project_id, key)
);
CREATE INDEX IF NOT EXISTS idx_project_custom_fields_project
  ON project_custom_fields(project_id, sort_order);

CREATE TABLE IF NOT EXISTS project_task_field_values (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id    TEXT NOT NULL REFERENCES project_tasks(task_id) ON DELETE CASCADE,
  field_id   TEXT NOT NULL REFERENCES project_custom_fields(field_id) ON DELETE CASCADE,
  value      TEXT NOT NULL DEFAULT '',
  updated_at INTEGER NOT NULL,
  UNIQUE(task_id, field_id)
);
CREATE INDEX IF NOT EXISTS idx_project_task_field_values_field
  ON project_task_field_values(field_id);

ALTER TABLE project_artifacts ADD COLUMN size INTEGER NOT NULL DEFAULT 0;
ALTER TABLE project_artifacts ADD COLUMN mime TEXT NOT NULL DEFAULT '';

UPDATE _schema_version SET version = 20;
