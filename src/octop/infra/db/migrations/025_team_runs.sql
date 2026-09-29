-- Schema v25: expert-team runs (pipeline state) + task findings + task/artifact columns.
--
-- Canonical v24 -> v25 DDL for SQLite. Applied by ``run_migrations``' generic SQL
-- path (``executescript``) -- ``migrate.py`` deliberately gains no ``_ensure_*``
-- helper for this version (the 020/022/023/024 precedent: the numbered SQL pair is
-- the canonical DDL). ``team_runs`` is the 1:1 extension row of the project a team
-- run owns: ``projects`` keeps the generic fields, ``team_runs`` keeps the pipeline
-- fields -- no second project entity.
--
-- NOTE on numbering: this migration was drafted as ``022``, but the comment line
-- claimed 022/023/024 first; per AGENTS.md section 7 the next free number is 025.
--
-- Timestamp columns are INTEGER unix seconds, matching 001_initial. Resource tables
-- use an integer surrogate ``id`` plus a public string ``{entity}_id``; child rows
-- FK the public string, never the integer id.
--
-- The "at most one lead per run" rule is a PARTIAL UNIQUE INDEX (``... WHERE
-- is_lead = 1``): SQLite and PG both reject a partial predicate inside an inline
-- table constraint, so it is emitted as a separate CREATE UNIQUE INDEX below.
--
-- Every ADD COLUMN below carries the DEFAULT its NOT NULL requires (SQLite rejects
-- ``ADD COLUMN ... NOT NULL`` without one). All of them are additive and nullable
-- or defaulted, so no table rebuild and no ``migrate.py`` helper is needed.

CREATE TABLE IF NOT EXISTS team_runs (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id            TEXT NOT NULL UNIQUE,
  team_agent_id     TEXT NOT NULL,
  project_id        TEXT NOT NULL UNIQUE REFERENCES projects(project_id) ON DELETE CASCADE,
  room_thread_id    TEXT,
  goal              TEXT NOT NULL DEFAULT '',
  mode              TEXT NOT NULL DEFAULT 'one-shot',
  deliverable       TEXT NOT NULL DEFAULT 'code+artifacts',
  tier              TEXT NOT NULL DEFAULT 'standard',
  status            TEXT NOT NULL DEFAULT 'running',
  phase             TEXT NOT NULL DEFAULT 'clarify',
  run_root          TEXT NOT NULL DEFAULT 'host_workspace',
  max_review_rounds INTEGER NOT NULL DEFAULT 3,
  max_test_rounds   INTEGER NOT NULL DEFAULT 3,
  created_by        INTEGER NOT NULL REFERENCES users(id),
  created_at        INTEGER NOT NULL,
  updated_at        INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_team_runs_team ON team_runs(team_agent_id, status);

CREATE TABLE IF NOT EXISTS team_run_phases (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id      TEXT NOT NULL REFERENCES team_runs(run_id) ON DELETE CASCADE,
  phase       TEXT NOT NULL,
  seq         INTEGER NOT NULL,
  status      TEXT NOT NULL DEFAULT 'pending',
  entered_at  INTEGER,
  passed_at   INTEGER,
  gate_detail TEXT NOT NULL DEFAULT '{}',
  UNIQUE(run_id, phase)
);

CREATE TABLE IF NOT EXISTS team_run_members (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id    TEXT NOT NULL REFERENCES team_runs(run_id) ON DELETE CASCADE,
  role      TEXT NOT NULL,
  agent_id  TEXT NOT NULL,
  is_lead   INTEGER NOT NULL DEFAULT 0,
  joined_at INTEGER NOT NULL,
  UNIQUE(run_id, role)
);

-- At most one lead (is_lead = 1) per run.
CREATE UNIQUE INDEX IF NOT EXISTS idx_team_run_members_lead
  ON team_run_members(run_id, is_lead) WHERE is_lead = 1;

CREATE TABLE IF NOT EXISTS project_task_findings (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  finding_id TEXT NOT NULL UNIQUE,
  task_id    TEXT NOT NULL,
  run_id     TEXT REFERENCES team_runs(run_id) ON DELETE CASCADE,
  round      INTEGER NOT NULL DEFAULT 1,
  severity   TEXT NOT NULL,
  title      TEXT NOT NULL,
  detail     TEXT NOT NULL DEFAULT '',
  verdict    TEXT,
  status     TEXT NOT NULL DEFAULT 'open',
  created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_findings_task ON project_task_findings(task_id, round);

ALTER TABLE project_tasks ADD COLUMN kind TEXT NOT NULL DEFAULT 'work';
ALTER TABLE project_tasks ADD COLUMN acceptance TEXT NOT NULL DEFAULT '[]';
ALTER TABLE project_tasks ADD COLUMN in_scope TEXT NOT NULL DEFAULT '[]';
ALTER TABLE project_tasks ADD COLUMN verify TEXT NOT NULL DEFAULT '[]';
ALTER TABLE project_tasks ADD COLUMN changed_paths TEXT NOT NULL DEFAULT '[]';
ALTER TABLE project_tasks ADD COLUMN round INTEGER NOT NULL DEFAULT 1;
ALTER TABLE project_tasks ADD COLUMN verdict TEXT;
ALTER TABLE project_tasks ADD COLUMN attempt INTEGER NOT NULL DEFAULT 0;
ALTER TABLE project_tasks ADD COLUMN attempt_id TEXT;
ALTER TABLE project_tasks ADD COLUMN claimed_by TEXT;
ALTER TABLE project_tasks ADD COLUMN claimed_at INTEGER;
ALTER TABLE project_tasks ADD COLUMN started_at INTEGER;
ALTER TABLE project_tasks ADD COLUMN phase TEXT;

ALTER TABLE project_artifacts ADD COLUMN owner_role TEXT;
ALTER TABLE project_artifacts ADD COLUMN phase TEXT;

ALTER TABLE threads ADD COLUMN pending_decision TEXT;

UPDATE _schema_version SET version = 25;
