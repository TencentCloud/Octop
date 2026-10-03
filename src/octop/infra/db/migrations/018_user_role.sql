-- Schema v18: role templates. users.role stores the template public id
-- (admin | user | custom ULID). Invites store the same id in user_invites.role.
-- Resource policies live in a JSON array; a missing name means that policy is off.
-- Existing users keep their role values (already admin|user).

CREATE TABLE IF NOT EXISTS user_role (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  user_role_id    TEXT NOT NULL UNIQUE,
  user_role_name  TEXT NOT NULL UNIQUE,
  description     TEXT,
  permissions     TEXT NOT NULL DEFAULT '[]',
  policies        TEXT NOT NULL DEFAULT '[]',
  avatar_icon     TEXT,
  created_at      INTEGER NOT NULL,
  updated_at      INTEGER NOT NULL
);

ALTER TABLE users ADD COLUMN role_name TEXT;
ALTER TABLE users ADD COLUMN avatar_icon TEXT;
ALTER TABLE user_invites ADD COLUMN role_name TEXT;
ALTER TABLE user_invites ADD COLUMN role TEXT;

ALTER TABLE threads ADD COLUMN archived INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_threads_agent_user_archived
  ON threads(agent_id, user_id, archived, pinned, last_active, created_at);

UPDATE _schema_version SET version = 18;
