-- One-time user invite codes (admin-issued; public redeem).

CREATE TABLE IF NOT EXISTS user_invites (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  code              TEXT NOT NULL UNIQUE,
  created_by        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  note              TEXT,
  created_at        INTEGER NOT NULL,
  expires_at        INTEGER NOT NULL,
  used_at           INTEGER,
  used_by_user_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
  revoked_at        INTEGER
);

CREATE INDEX IF NOT EXISTS idx_user_invites_created_at ON user_invites(created_at DESC);

UPDATE _schema_version SET version = 9;
