-- Schema v15: pluggable SSO providers (kind + extra JSON) and multi-identity
-- links. SQLite applies this via migrate.py ensure helpers (idempotent).

ALTER TABLE sso_providers ADD COLUMN kind TEXT NOT NULL DEFAULT 'oidc';
ALTER TABLE sso_providers ADD COLUMN extra TEXT NOT NULL DEFAULT '{}';
CREATE UNIQUE INDEX IF NOT EXISTS idx_sso_providers_kind ON sso_providers(kind);

CREATE TABLE IF NOT EXISTS user_sso_identities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider_id INTEGER NOT NULL REFERENCES sso_providers(id) ON DELETE CASCADE,
  subject TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  UNIQUE(user_id, provider_id),
  UNIQUE(provider_id, subject)
);

INSERT OR IGNORE INTO user_sso_identities (user_id, provider_id, subject, created_at)
SELECT id, sso_provider_id, sso_subject, created_at
FROM users
WHERE sso_provider_id IS NOT NULL AND sso_subject IS NOT NULL;

UPDATE _schema_version SET version = 15;
