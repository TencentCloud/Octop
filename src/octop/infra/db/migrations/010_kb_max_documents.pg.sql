-- Schema v10: per-knowledge-base configurable document limit.
-- PostgreSQL: ADD COLUMN IF NOT EXISTS is safe (skips if already present).

ALTER TABLE knowledge_bases
  ADD COLUMN IF NOT EXISTS max_documents INTEGER NOT NULL DEFAULT 100;

UPDATE _schema_version SET version = 10;
