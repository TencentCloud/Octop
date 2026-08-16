-- Schema v7: per-expert control over whether installers may view skill details.
ALTER TABLE published_experts ADD COLUMN allow_skill_details INTEGER NOT NULL DEFAULT 1;

UPDATE _schema_version SET version = 7;
