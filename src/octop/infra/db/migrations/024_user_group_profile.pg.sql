-- Schema v24: user groups can be disabled and can carry a preset avatar.

ALTER TABLE user_group ADD COLUMN IF NOT EXISTS enabled INTEGER NOT NULL DEFAULT 1;
ALTER TABLE user_group ADD COLUMN IF NOT EXISTS avatar_icon TEXT;

UPDATE _schema_version SET version = 24;
