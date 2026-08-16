ALTER TABLE users ADD COLUMN permissions TEXT NOT NULL DEFAULT '[]';

UPDATE _schema_version SET version = 6;
