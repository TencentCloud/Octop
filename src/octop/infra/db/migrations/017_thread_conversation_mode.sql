-- Schema v17: sticky Ask/Plan/Craft mode, pending plan file, HITL bypass,
-- and durable HITL pending records.

ALTER TABLE threads ADD COLUMN conversation_mode TEXT;
ALTER TABLE threads ADD COLUMN pending_plan_path TEXT;
ALTER TABLE threads ADD COLUMN hitl_policy TEXT;

-- Durable HITL pending records (folded into this unreleased pair instead of
-- opening 018; migrate._ensure_hitl_pending_schema backfills the table on
-- databases that already recorded v17 before the DDL landed here).

CREATE TABLE IF NOT EXISTS hitl_pending_records (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  pending_id         TEXT    NOT NULL UNIQUE,
  thread_id          TEXT    NOT NULL,
  agent_id           TEXT    NOT NULL,
  user_id            INTEGER NOT NULL,
  session_key        TEXT    NOT NULL,
  channel_type       TEXT    NOT NULL,
  action_requests    TEXT    NOT NULL DEFAULT '[]',
  review_configs     TEXT,
  created_at         REAL    NOT NULL,
  status             TEXT    NOT NULL DEFAULT 'pending',
  ask_question_index INTEGER NOT NULL DEFAULT 0,
  ask_answers        TEXT    NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_hitl_pending_records_session
  ON hitl_pending_records(session_key, status);

CREATE INDEX IF NOT EXISTS idx_hitl_pending_records_thread
  ON hitl_pending_records(thread_id, status);

UPDATE _schema_version SET version = 17;
