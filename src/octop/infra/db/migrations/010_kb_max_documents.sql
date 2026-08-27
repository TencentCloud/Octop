-- Schema v10: per-knowledge-base configurable document limit.
-- The column is added by migrate.py::_ensure_knowledge_bases_schema so that
-- boot-time repair covers pre-v10 databases. This file only bumps _schema_version.
-- 100 is the previous system-wide default; 0 means unlimited.

UPDATE _schema_version SET version = 10;
