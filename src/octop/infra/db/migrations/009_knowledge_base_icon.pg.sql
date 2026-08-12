-- Schema v9: knowledge base preset icon.
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS icon_name TEXT NOT NULL DEFAULT '';

UPDATE _schema_version SET version = 9;
