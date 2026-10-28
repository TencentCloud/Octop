-- Schema v25: repair historical TEXT rows in connectors and bridge_connections.
-- A pre-1.0.3b1 custom-MCP save path wrote credential_blob as TEXT (the
-- encrypt_credentials envelope bytes, encoded as UTF-8 text) and updated_at
-- as an ISO timestamp string instead of a unix integer. The read-side fix in
-- connectors.py / bridge_connections.py tolerates TEXT blobs; this migration
-- repairs the stored data so the column types match the schema contract again.

-- Convert TEXT credential_blob back to BLOB. CAST(TEXT AS BLOB) in SQLite
-- interprets each character as its UTF-8 byte (the inverse of utf-8 encode).
UPDATE connectors
SET credential_blob = CAST(credential_blob AS BLOB)
WHERE credential_blob IS NOT NULL AND typeof(credential_blob) = 'text';

UPDATE bridge_connections
SET credential_blob = CAST(credential_blob AS BLOB)
WHERE credential_blob IS NOT NULL AND typeof(credential_blob) = 'text';

-- Convert ISO-text updated_at to unix integer timestamps. Only SQLite has
-- this variant; PostgreSQL stores typed timestamps natively.
-- ISO strings like '2026-10-27T19:54:22.418170' → strftime '%s'.
UPDATE connectors
SET updated_at = CAST(strftime('%s', updated_at) AS INTEGER)
WHERE typeof(updated_at) = 'text' AND updated_at REGEXP '^\d{4}-\d{2}-\d{2}T';

UPDATE bridge_connections
SET updated_at = CAST(strftime('%s', updated_at) AS INTEGER)
WHERE typeof(updated_at) = 'text' AND updated_at REGEXP '^\d{4}-\d{2}-\d{2}T';

UPDATE _schema_version SET version = 25;