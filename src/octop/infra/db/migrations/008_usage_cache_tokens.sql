ALTER TABLE usage_log ADD COLUMN uncached_input_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE usage_log ADD COLUMN cache_read_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE usage_log ADD COLUMN cache_write_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE usage_log ADD COLUMN reasoning_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE usage_log ADD COLUMN model_calls INTEGER NOT NULL DEFAULT 1;

UPDATE usage_log
SET uncached_input_tokens = input_tokens
WHERE uncached_input_tokens = 0
  AND input_tokens > 0
  AND cache_read_tokens = 0
  AND cache_write_tokens = 0;

UPDATE _schema_version SET version = 8;
