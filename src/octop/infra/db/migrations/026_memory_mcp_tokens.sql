-- 026: retire the user-level memory MCP token table.
--
-- Token ownership moved to the standalone octop-memory service; existing
-- tokens are migrated with tools/migrate_octop_tokens.py (hash-preserving).
-- Keep the migration number so schema versions stay stable.
DROP TABLE IF EXISTS memory_mcp_tokens;

UPDATE _schema_version SET version = 26;
