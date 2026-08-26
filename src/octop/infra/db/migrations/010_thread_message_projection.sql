-- Dashboard history read model. Existing message-bearing threads are backfilled lazily;
-- new/empty threads can use the projection immediately.

CREATE TABLE IF NOT EXISTS thread_messages (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id     TEXT NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
  seq           INTEGER NOT NULL,
  message_id    TEXT,
  role          TEXT NOT NULL,
  message_json  TEXT NOT NULL,
  created_at    INTEGER NOT NULL,
  UNIQUE(thread_id, seq),
  UNIQUE(thread_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_thread_messages_thread_seq
  ON thread_messages(thread_id, seq DESC);

CREATE TABLE IF NOT EXISTS thread_history_projection (
  thread_id    TEXT PRIMARY KEY REFERENCES threads(thread_id) ON DELETE CASCADE,
  status       TEXT NOT NULL,
  updated_at   INTEGER NOT NULL,
  error        TEXT
);

INSERT OR IGNORE INTO thread_history_projection(thread_id, status, updated_at, error)
SELECT thread_id,
       CASE WHEN last_active > 0 OR title IS NOT NULL THEN 'pending' ELSE 'ready' END,
       CAST(strftime('%s', 'now') AS INTEGER),
       NULL
FROM threads;

UPDATE _schema_version SET version = 10;
