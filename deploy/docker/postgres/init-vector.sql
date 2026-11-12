-- Instance-level init only (docker-entrypoint-initdb.d on first volume).
-- NOT part of Octop control-plane migrations (see ADR 002).
-- Optional for local/dev pgvector image; control plane does not require it.
-- Managed Postgres: enable via your provider / DBA if embeddings need pgvector.
CREATE EXTENSION IF NOT EXISTS vector;
