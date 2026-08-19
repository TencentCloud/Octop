ALTER TABLE published_experts ADD COLUMN allow_skill_details BOOLEAN NOT NULL DEFAULT TRUE;

UPDATE _schema_version SET version = 7;
