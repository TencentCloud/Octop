-- Schema v13: multi-instance and shared connectors.

PRAGMA foreign_keys = OFF;

ALTER TABLE connectors RENAME TO connectors_legacy;

CREATE TABLE connectors (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  instance_id           TEXT NOT NULL UNIQUE,
  user_id               INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind                  TEXT NOT NULL,
  display_name          TEXT NOT NULL,
  status                TEXT NOT NULL DEFAULT 'active',
  shared                INTEGER NOT NULL DEFAULT 0,
  mcp_server_name       TEXT NOT NULL UNIQUE,
  credential_blob       BLOB,
  credential_expires_at INTEGER,
  credential_rotated_at INTEGER,
  config_json           TEXT,
  created_at            INTEGER NOT NULL,
  updated_at            INTEGER NOT NULL
);

INSERT INTO connectors(
  id, instance_id, user_id, kind, display_name, status, shared,
  mcp_server_name, credential_blob, credential_expires_at,
  credential_rotated_at, config_json, created_at, updated_at
)
SELECT
  id, instance_id, user_id, kind,
  CASE
    WHEN kind = 'custom-mcp' THEN display_name
    WHEN ROW_NUMBER() OVER (
      PARTITION BY user_id, display_name ORDER BY id
    ) = 1 THEN display_name
    ELSE display_name || ' (' || substr(instance_id, -6) || ')'
  END,
  status, 0,
  mcp_server_name, credential_blob, credential_expires_at,
  credential_rotated_at, config_json, created_at, updated_at
FROM connectors_legacy;

DROP TABLE connectors_legacy;

CREATE INDEX idx_connectors_user ON connectors(user_id);
CREATE INDEX idx_connectors_shared ON connectors(shared) WHERE shared = 1;
CREATE UNIQUE INDEX idx_connectors_user_display_name
  ON connectors(user_id, display_name) WHERE kind <> 'custom-mcp';

PRAGMA foreign_keys = ON;

UPDATE _schema_version SET version = 13;
