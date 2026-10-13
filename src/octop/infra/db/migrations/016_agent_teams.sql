-- Schema v16: team hosts are ordinary agents with kind=team.
-- Roster lives in the host workspace `.octop/manifest.json`, not a member table.

ALTER TABLE agents ADD COLUMN kind TEXT NOT NULL DEFAULT 'expert';

UPDATE _schema_version SET version = 16;
