-- Schema v8: knowledge base metadata, ACL members, and document rows.
-- Applied idempotently via migrate._ensure_knowledge_bases_schema on SQLite;
-- this file documents the target schema (and is used by tests / tooling).
CREATE TABLE IF NOT EXISTS knowledge_bases (
  id TEXT PRIMARY KEY,
  owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  default_open INTEGER NOT NULL DEFAULT 0,
  shared INTEGER NOT NULL DEFAULT 0,
  embedding_model TEXT NOT NULL DEFAULT '',
  embedding_dim INTEGER NOT NULL DEFAULT 0,
  doc_count INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE(owner_user_id, name)
);
CREATE INDEX IF NOT EXISTS idx_knowledge_bases_owner ON knowledge_bases(owner_user_id);

CREATE TABLE IF NOT EXISTS knowledge_base_members (
  kb_id TEXT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (kb_id, user_id)
);

CREATE TABLE IF NOT EXISTS knowledge_documents (
  id TEXT PRIMARY KEY,
  kb_id TEXT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  content_type TEXT NOT NULL,
  byte_size INTEGER NOT NULL,
  content_hash TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending',
  error_message TEXT NOT NULL DEFAULT '',
  chunk_count INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_knowledge_documents_kb ON knowledge_documents(kb_id);

UPDATE _schema_version SET version = 8;
