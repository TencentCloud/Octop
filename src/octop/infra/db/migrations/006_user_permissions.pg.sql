ALTER TABLE users ADD COLUMN permissions JSONB NOT NULL DEFAULT '[]'::jsonb;

UPDATE _schema_version SET version = 6;
