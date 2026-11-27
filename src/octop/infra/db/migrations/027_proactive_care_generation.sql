-- Per-agent model, reasoning effort and deadline for proactive care generation.
ALTER TABLE proactive_care_config ADD COLUMN model_ref TEXT;
ALTER TABLE proactive_care_config ADD COLUMN reasoning_effort TEXT NOT NULL DEFAULT 'auto';
ALTER TABLE proactive_care_config ADD COLUMN generation_timeout_seconds INTEGER NOT NULL DEFAULT 30;
UPDATE _schema_version SET version = 27;
