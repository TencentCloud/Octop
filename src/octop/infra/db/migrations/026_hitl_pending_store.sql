-- Schema v26: HITL pending store persistence (SQLite dialect).

CREATE TABLE IF NOT EXISTS hitl_pending_records (
  id                        INTEGER PRIMARY KEY AUTOINCREMENT,
  pending_id                TEXT NOT NULL UNIQUE,
  thread_id                 TEXT NOT NULL,
  agent_id                  TEXT NOT NULL,
  user_id                   TEXT NOT NULL,
  session_key               TEXT NOT NULL,
  channel_type              TEXT NOT NULL DEFAULT '',
  action_requests           TEXT NOT NULL DEFAULT '[]',
  review_configs            TEXT,
  status                    TEXT NOT NULL DEFAULT 'pending',
  ask_question_index        INTEGER NOT NULL DEFAULT 0,
  ask_answers               TEXT,
  resume_agent_id           TEXT,
  resume_thread_id          TEXT,
  form_context              TEXT,
  consumed_submission_ids   TEXT NOT NULL DEFAULT '[]',
  created_at                REAL NOT NULL,
  updated_at                REAL NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_hpr_session_agent_created
  ON hitl_pending_records(session_key, agent_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_hpr_thread_id
  ON hitl_pending_records(thread_id);

CREATE INDEX IF NOT EXISTS idx_hpr_resume_thread_id
  ON hitl_pending_records(resume_thread_id);

CREATE INDEX IF NOT EXISTS idx_hpr_agent_user_status
  ON hitl_pending_records(agent_id, user_id, status);

CREATE INDEX IF NOT EXISTS idx_hpr_status_created
  ON hitl_pending_records(status, created_at);

CREATE INDEX IF NOT EXISTS idx_hpr_slot
  ON hitl_pending_records(session_key, thread_id, resume_agent_id);

UPDATE _schema_version SET version = 26;
