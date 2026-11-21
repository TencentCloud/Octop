-- 026: retire the user-level memory MCP token table (see the SQLite variant).
DROP TABLE IF EXISTS memory_mcp_tokens;

UPDATE _schema_version SET version = 26;
