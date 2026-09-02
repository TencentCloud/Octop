-- Schema v11: append-only chat trajectory event log.

CREATE TABLE IF NOT EXISTS trajectory_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL UNIQUE,
  agent_id TEXT NOT NULL,
  thread_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  ts REAL NOT NULL,
  kind TEXT NOT NULL,
  turn_id TEXT,
  request_seq INTEGER,
  is_error INTEGER NOT NULL DEFAULT 0,
  summary TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL DEFAULT '{}',
  UNIQUE (thread_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_trajectory_events_thread_seq
  ON trajectory_events (thread_id, seq);

UPDATE _schema_version SET version = 11;
