-- Schema v7: OIDC SSO providers, login states, and user identities.
CREATE TABLE IF NOT EXISTS sso_providers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  enabled INTEGER NOT NULL DEFAULT 0,
  display_name TEXT NOT NULL DEFAULT '',
  issuer TEXT NOT NULL DEFAULT '',
  client_id TEXT NOT NULL DEFAULT '',
  client_secret_enc BLOB,
  scopes TEXT NOT NULL DEFAULT 'openid profile email',
  dashboard_origin TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sso_login_states (
  state TEXT PRIMARY KEY,
  provider_id INTEGER NOT NULL REFERENCES sso_providers(id) ON DELETE CASCADE,
  nonce TEXT NOT NULL,
  code_verifier TEXT NOT NULL,
  redirect_after TEXT NOT NULL DEFAULT '/chat',
  login_code TEXT,
  user_id INTEGER,
  expires_at INTEGER NOT NULL,
  consumed_at INTEGER,
  created_at INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sso_login_states_login_code
  ON sso_login_states(login_code) WHERE login_code IS NOT NULL;

PRAGMA foreign_keys = OFF;

CREATE TABLE users_new (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  username            TEXT NOT NULL,
  password_hash       TEXT,
  role                TEXT NOT NULL,
  display_name        TEXT,
  disabled            INTEGER NOT NULL DEFAULT 0,
  locale              TEXT NOT NULL DEFAULT 'zh',
  created_at          INTEGER NOT NULL,
  login_failed_count  INTEGER NOT NULL DEFAULT 0,
  login_locked_until  INTEGER NOT NULL DEFAULT 0,
  preferences_json    TEXT NOT NULL DEFAULT '{}',
  email               TEXT,
  sso_provider_id     INTEGER REFERENCES sso_providers(id),
  sso_subject         TEXT
);

INSERT INTO users_new (
  id,
  username,
  password_hash,
  role,
  display_name,
  disabled,
  locale,
  created_at,
  login_failed_count,
  login_locked_until,
  preferences_json
)
SELECT
  id,
  username,
  password_hash,
  role,
  display_name,
  disabled,
  locale,
  created_at,
  login_failed_count,
  login_locked_until,
  preferences_json
FROM users;

DROP TABLE users;
ALTER TABLE users_new RENAME TO users;

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email
  ON users(email) WHERE email IS NOT NULL AND email != '';
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_sso
  ON users(sso_provider_id, sso_subject)
  WHERE sso_provider_id IS NOT NULL AND sso_subject IS NOT NULL;

PRAGMA foreign_keys = ON;

UPDATE _schema_version SET version = 7;
