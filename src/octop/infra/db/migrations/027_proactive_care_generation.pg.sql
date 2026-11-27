-- Per-agent model, reasoning effort and deadline for proactive care generation.
ALTER TABLE IF EXISTS proactive_care_config ADD COLUMN IF NOT EXISTS model_ref TEXT;
ALTER TABLE IF EXISTS proactive_care_config ADD COLUMN IF NOT EXISTS reasoning_effort TEXT NOT NULL DEFAULT 'auto';
ALTER TABLE IF EXISTS proactive_care_config ADD COLUMN IF NOT EXISTS generation_timeout_seconds INTEGER NOT NULL DEFAULT 30;
UPDATE _schema_version SET version = 27;
