-- Schema v25: GitHub-style MFA (TOTP, WebAuthn/passkeys, recovery codes) and
-- DB-backed auth challenges. SQLite applies this through _ensure_user_mfa_schema
-- so a replay onto a database that already has the columns/tables does not fail.

ALTER TABLE users ADD COLUMN mfa_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN mfa_failed_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN mfa_locked_until INTEGER NOT NULL DEFAULT 0;

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

UPDATE _schema_version SET version = 25;
