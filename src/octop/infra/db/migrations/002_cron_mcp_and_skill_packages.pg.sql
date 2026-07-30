-- Schema v2: cron MCP connector selection + global skill package metadata
-- (including package icons and unique package names).
ALTER TABLE cron_jobs ADD COLUMN IF NOT EXISTS mcp_servers TEXT NOT NULL DEFAULT '[]';

CREATE TABLE IF NOT EXISTS skill_packages (
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

ALTER TABLE skill_packages ADD COLUMN IF NOT EXISTS icon_name TEXT NOT NULL DEFAULT '';
ALTER TABLE skill_packages ADD COLUMN IF NOT EXISTS icon_url TEXT NOT NULL DEFAULT '';
CREATE UNIQUE INDEX IF NOT EXISTS idx_skill_packages_name ON skill_packages(name);

UPDATE _schema_version SET version = 2;
