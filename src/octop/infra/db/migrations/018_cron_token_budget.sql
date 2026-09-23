-- Schema v18: per-cron rolling 24h token budget (opt-in circuit breaker, #1014).

ALTER TABLE cron_jobs ADD COLUMN token_budget_24h INTEGER;
ALTER TABLE cron_jobs ADD COLUMN budget_tokens_used INTEGER NOT NULL DEFAULT 0;
ALTER TABLE cron_jobs ADD COLUMN budget_window_started_at INTEGER;

UPDATE _schema_version SET version = 18;
