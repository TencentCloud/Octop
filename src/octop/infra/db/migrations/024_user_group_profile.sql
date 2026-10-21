-- Schema v24: user groups can be disabled and can carry a preset avatar;
-- knowledge bases and bridge connections gain an optional uploaded/remote icon_url.
-- SQLite applies this through _ensure_user_group_profile_schema /
-- _ensure_knowledge_base_icon_url_schema / _ensure_bridge_icon_url_schema so a
-- replay onto a database that already has the columns does not fail.

ALTER TABLE user_group ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1;
ALTER TABLE user_group ADD COLUMN avatar_icon TEXT;
ALTER TABLE knowledge_bases ADD COLUMN icon_url TEXT NOT NULL DEFAULT '';
ALTER TABLE bridge_connections ADD COLUMN icon_url TEXT NOT NULL DEFAULT '';

UPDATE _schema_version SET version = 24;
