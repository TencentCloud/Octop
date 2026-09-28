-- Schema v24: structured mentions on a comment.
--
-- Canonical v23 -> v24 DDL for SQLite. The dashboard sends the picked actors as
-- structured data and the server **stores it verbatim** (design decision P1 = (c)):
-- no body scanning, no server-side parsing. The column is nullable, so every
-- existing comment means "no mentions".
--
-- Additive column only -- no rebuild, no ``migrate.py`` helper (the 022/023
-- precedent).

ALTER TABLE project_comments ADD COLUMN mentions TEXT;

UPDATE _schema_version SET version = 24;
