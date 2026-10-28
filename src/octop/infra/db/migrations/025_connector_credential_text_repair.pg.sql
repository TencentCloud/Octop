-- Schema v25 (PostgreSQL): repair historical BYTEA-cast TEXT rows.
-- PostgreSQL does not allow storing 'text' in a BYTEA column natively, but
-- TEXT could be written through bypass paths. Find any rows where the stored
-- value is actually text and cast back to bytea.

UPDATE connectors
SET credential_blob = credential_blob::text::bytea
WHERE credential_blob IS NOT NULL
  AND pg_typeof(credential_blob) = 'text';

UPDATE bridge_connections
SET credential_blob = credential_blob::text::bytea
WHERE credential_blob IS NOT NULL
  AND pg_typeof(credential_blob) = 'text';

-- updated_at should be a BIGINT epoch. If it's a TEXT ISO timestamp, convert.
UPDATE connectors
SET updated_at = EXTRACT(EPOCH FROM (updated_at::timestamptz))::bigint
WHERE pg_typeof(updated_at) = 'text'
  AND updated_at ~ '^\d{4}-\d{2}-\d{2}T';

UPDATE bridge_connections
SET updated_at = EXTRACT(EPOCH FROM (updated_at::timestamptz))::bigint
WHERE pg_typeof(updated_at) = 'text'
  AND updated_at ~ '^\d{4}-\d{2}-\d{2}T';

UPDATE _schema_version SET version = 25;