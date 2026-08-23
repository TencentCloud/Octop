-- Schema v7: agent profile columns, thread artifacts, integer PK + public
-- string ids for knowledge / skill packages / published experts, document
-- folders (path), drop unused knowledge_base_members.
--
-- This file is the canonical v6 → v7 upgrade for a database that still has
-- TEXT primary keys on those resource tables (the v2/v5 shapes).
-- PostgreSQL applies the matching ``.pg.sql`` file.
-- SQLite applies equivalent idempotent helpers in migrate.py because
-- ``ADD COLUMN`` is not ``IF NOT EXISTS`` and boot repair may already have
-- applied parts of v7; a clean v6 SQLite DB can still execute this file.
-- Profile values still in ``agents.config_json`` are backfilled in Python.

ALTER TABLE agents ADD COLUMN color TEXT;
ALTER TABLE agents ADD COLUMN icon_name TEXT;
ALTER TABLE agents ADD COLUMN icon_url TEXT;
ALTER TABLE agents ADD COLUMN skill_package_ids TEXT;
ALTER TABLE agents ADD COLUMN published_expert_id TEXT;
ALTER TABLE agents ADD COLUMN welcome_message TEXT;
ALTER TABLE threads ADD COLUMN artifacts TEXT NOT NULL DEFAULT '[]';
DROP TABLE IF EXISTS knowledge_base_members;

PRAGMA foreign_keys = OFF;

ALTER TABLE skill_packages RENAME TO skill_packages_legacy;
CREATE TABLE skill_packages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  skill_package_id TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  created_by TEXT NOT NULL,
  skill_count INTEGER NOT NULL DEFAULT 0,
  icon_name TEXT NOT NULL DEFAULT '',
  icon_url TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
INSERT INTO skill_packages(
  skill_package_id, name, description, created_by, skill_count,
  icon_name, icon_url, created_at, updated_at
)
SELECT id, name, description, created_by, skill_count,
  COALESCE(icon_name, ''), COALESCE(icon_url, ''), created_at, updated_at
FROM skill_packages_legacy;
DROP TABLE skill_packages_legacy;
CREATE UNIQUE INDEX IF NOT EXISTS idx_skill_packages_name ON skill_packages(name);

ALTER TABLE published_experts RENAME TO published_experts_legacy;
CREATE TABLE published_experts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  published_expert_id TEXT NOT NULL UNIQUE,
  slug TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  created_by TEXT NOT NULL,
  source_agent_id TEXT,
  icon_name TEXT NOT NULL DEFAULT '',
  color TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
INSERT INTO published_experts(
  published_expert_id, slug, name, description, created_by,
  source_agent_id, icon_name, color, created_at, updated_at
)
SELECT id, slug, name, description, created_by,
  source_agent_id, COALESCE(icon_name, ''), COALESCE(color, ''),
  created_at, updated_at
FROM published_experts_legacy;
DROP TABLE published_experts_legacy;
CREATE UNIQUE INDEX IF NOT EXISTS idx_published_experts_slug ON published_experts(slug);
CREATE INDEX IF NOT EXISTS idx_published_experts_created_by ON published_experts(created_by);

ALTER TABLE knowledge_bases RENAME TO knowledge_bases_legacy;
ALTER TABLE knowledge_documents RENAME TO knowledge_documents_legacy;
CREATE TABLE knowledge_bases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  knowledge_base_id TEXT NOT NULL UNIQUE,
  owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  default_open INTEGER NOT NULL DEFAULT 0,
  shared INTEGER NOT NULL DEFAULT 0,
  icon_name TEXT NOT NULL DEFAULT '',
  embedding_model TEXT NOT NULL DEFAULT '',
  embedding_dim INTEGER NOT NULL DEFAULT 0,
  doc_count INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE(owner_user_id, name)
);
INSERT INTO knowledge_bases(
  knowledge_base_id, owner_user_id, name, description, default_open,
  shared, icon_name, embedding_model, embedding_dim, doc_count,
  created_at, updated_at
)
SELECT id, owner_user_id, name, description, default_open,
  COALESCE(shared, 0), COALESCE(icon_name, ''), embedding_model,
  embedding_dim, doc_count, created_at, updated_at
FROM knowledge_bases_legacy;
CREATE TABLE knowledge_documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id TEXT NOT NULL UNIQUE,
  kb_id TEXT NOT NULL REFERENCES knowledge_bases(knowledge_base_id) ON DELETE CASCADE,
  path TEXT NOT NULL,
  filename TEXT NOT NULL,
  is_dir INTEGER NOT NULL DEFAULT 0,
  content_type TEXT NOT NULL,
  byte_size INTEGER NOT NULL,
  content_hash TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending',
  error_message TEXT NOT NULL DEFAULT '',
  chunk_count INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE(kb_id, path)
);
INSERT INTO knowledge_documents(
  document_id, kb_id, path, filename, is_dir, content_type, byte_size,
  content_hash, status, error_message, chunk_count, created_at, updated_at
)
SELECT id, kb_id, filename, filename, 0, content_type, byte_size,
  content_hash, status, error_message, chunk_count, created_at, updated_at
FROM knowledge_documents_legacy;
DROP TABLE knowledge_documents_legacy;
DROP TABLE knowledge_bases_legacy;
CREATE INDEX IF NOT EXISTS idx_knowledge_bases_owner ON knowledge_bases(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_documents_kb ON knowledge_documents(kb_id);

PRAGMA foreign_keys = ON;

UPDATE _schema_version SET version = 7;
