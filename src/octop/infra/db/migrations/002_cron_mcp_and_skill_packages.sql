-- Schema v2: cron MCP connector selection + global skill package metadata
-- (including package icons and unique package names).
-- SQLite applies this via migrate.py helpers for idempotent partial upgrades.
ALTER TABLE cron_jobs ADD COLUMN mcp_servers TEXT NOT NULL DEFAULT '[]';

CREATE TABLE skill_packages (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  created_by TEXT NOT NULL,
  skill_count INTEGER NOT NULL DEFAULT 0,
  icon_name TEXT NOT NULL DEFAULT '',
  icon_url TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX idx_skill_packages_name ON skill_packages(name);

UPDATE _schema_version SET version = 2;
