-- 026: user-level memory MCP tokens are retired here.
--
-- The table is intentionally NOT dropped: existing installations still need
-- it as the source for tools/migrate_octop_tokens.py (hash-preserving move to
-- the standalone octop-memory service). Fresh databases never create it.
-- Keep the version marker so schema versions stay stable.
UPDATE _schema_version SET version = 26;
