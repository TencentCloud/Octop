-- Schema v25: GitHub-style MFA (TOTP, WebAuthn/passkeys, recovery codes),
-- DB-backed auth challenges, and same-row cron/channel leases. SQLite applies
-- this through idempotent ensure helpers so a replay does not fail.

ALTER TABLE users ADD COLUMN mfa_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN mfa_failed_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN mfa_locked_until INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN password_version INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS user_totp (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id             INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  secret_enc          BLOB NOT NULL,
  verified_at         INTEGER,
  pending_expires_at  INTEGER,
  last_used_step      INTEGER,
  created_at          INTEGER NOT NULL,
  updated_at          INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS user_webauthn_credentials (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  credential_id       TEXT NOT NULL UNIQUE,
  user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  public_key          BLOB NOT NULL,
  user_handle         TEXT NOT NULL,
  rp_id               TEXT NOT NULL,
  aaguid              TEXT,
  sign_count          INTEGER NOT NULL DEFAULT 0,
  backup_eligible     INTEGER NOT NULL DEFAULT 0,
  backup_state        INTEGER NOT NULL DEFAULT 0,
  name                TEXT,
  transports_json     TEXT NOT NULL DEFAULT '[]',
  created_at          INTEGER NOT NULL,
  last_used_at        INTEGER
);

CREATE INDEX IF NOT EXISTS idx_user_webauthn_user_id
  ON user_webauthn_credentials(user_id);

CREATE TABLE IF NOT EXISTS user_recovery_codes (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  code_hash           TEXT NOT NULL,
  used_at             INTEGER,
  created_at          INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_recovery_codes_user_id
  ON user_recovery_codes(user_id);

CREATE TABLE IF NOT EXISTS auth_challenges (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  challenge           TEXT UNIQUE,
  jti                 TEXT UNIQUE,
  kind                TEXT NOT NULL,
  user_id             INTEGER REFERENCES users(id) ON DELETE CASCADE,
  attempts            INTEGER NOT NULL DEFAULT 0,
  expires_at          INTEGER NOT NULL,
  consumed_at         INTEGER,
  created_at          INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_auth_challenges_expires_at
  ON auth_challenges(expires_at);

ALTER TABLE cron_jobs ADD COLUMN run_lease_owner TEXT;
ALTER TABLE cron_jobs ADD COLUMN run_lease_token TEXT;
ALTER TABLE cron_jobs ADD COLUMN run_lease_until INTEGER;

ALTER TABLE channels ADD COLUMN runtime_lease_owner TEXT;
ALTER TABLE channels ADD COLUMN runtime_lease_token TEXT;
ALTER TABLE channels ADD COLUMN runtime_lease_until INTEGER;
ALTER TABLE channels ADD COLUMN runtime_generation INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS profile_avatars (
  owner_kind TEXT NOT NULL,
  owner_id TEXT NOT NULL,
  media_type TEXT NOT NULL,
  content BLOB NOT NULL,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (owner_kind, owner_id)
);

CREATE TABLE IF NOT EXISTS control_files (
  namespace TEXT NOT NULL,
  owner_id TEXT NOT NULL,
  path TEXT NOT NULL,
  content BLOB NOT NULL,
  PRIMARY KEY (namespace, owner_id, path)
);

UPDATE _schema_version SET version = 25;
