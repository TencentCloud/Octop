-- Schema v24: user groups can be disabled and can carry a preset avatar;
-- knowledge bases and bridge connections gain an optional uploaded/remote icon_url;
-- bridge connections gain shared (who can use the link).

ALTER TABLE user_group ADD COLUMN IF NOT EXISTS enabled INTEGER NOT NULL DEFAULT 1;
ALTER TABLE user_group ADD COLUMN IF NOT EXISTS avatar_icon TEXT;
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS icon_url TEXT NOT NULL DEFAULT '';
ALTER TABLE bridge_connections ADD COLUMN IF NOT EXISTS icon_url TEXT NOT NULL DEFAULT '';
ALTER TABLE bridge_connections ADD COLUMN IF NOT EXISTS shared INTEGER NOT NULL DEFAULT 0;

UPDATE _schema_version SET version = 24;
