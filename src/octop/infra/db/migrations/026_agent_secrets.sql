-- Schema v26: per-agent secret slots collected from chat via the masked
-- ``request_secret_input`` card. Values are Fernet-encrypted blobs keyed by
-- PURPOSE_AGENT_SECRET; plaintext never enters chat history or model context.

CREATE TABLE IF NOT EXISTS agent_secrets (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  secret_id     TEXT NOT NULL UNIQUE,
  agent_id      TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
  user_id       INTEGER NOT NULL,
  slot_name     TEXT NOT NULL,
  display_name  TEXT,
  secret_blob   BLOB NOT NULL,
  created_at    INTEGER NOT NULL,
  rotated_at    INTEGER,
  updated_at    INTEGER NOT NULL,
  UNIQUE(agent_id, slot_name)
);

CREATE INDEX IF NOT EXISTS idx_agent_secrets_agent
  ON agent_secrets(agent_id);

UPDATE _schema_version SET version = 26;
