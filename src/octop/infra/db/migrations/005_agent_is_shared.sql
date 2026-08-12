-- Schema v5: shared expert runtime flag on agents.
ALTER TABLE agents ADD COLUMN is_shared INTEGER NOT NULL DEFAULT 0;
CREATE INDEX idx_agents_shared ON agents(is_shared) WHERE is_shared = 1;

UPDATE _schema_version SET version = 5;
