-- Schema v24: user groups can be disabled and can carry a preset avatar.
-- SQLite applies this through _ensure_user_group_profile_schema so a replay
-- onto a database that already has the columns does not fail.

ALTER TABLE user_group ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1;
ALTER TABLE user_group ADD COLUMN avatar_icon TEXT;

UPDATE _schema_version SET version = 24;
