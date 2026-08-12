-- Schema v6: user-published expert templates.
CREATE TABLE IF NOT EXISTS published_experts (
  id              TEXT PRIMARY KEY,
  slug            TEXT NOT NULL,
  name            TEXT NOT NULL,
  description     TEXT NOT NULL DEFAULT '',
  created_by      TEXT NOT NULL,
  source_agent_id TEXT,
  icon_name       TEXT NOT NULL DEFAULT '',
  color           TEXT NOT NULL DEFAULT '',
  created_at      BIGINT NOT NULL,
  updated_at      BIGINT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_published_experts_slug ON published_experts(slug);
CREATE INDEX IF NOT EXISTS idx_published_experts_created_by ON published_experts(created_by);

UPDATE _schema_version SET version = 6;
