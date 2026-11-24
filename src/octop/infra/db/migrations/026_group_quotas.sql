CREATE TABLE IF NOT EXISTS group_quotas (
    group_id        INTEGER PRIMARY KEY,
    quota_tokens    INTEGER NOT NULL,
    used_tokens     INTEGER NOT NULL DEFAULT 0,
    alert_threshold REAL DEFAULT 0.8,
    period          TEXT DEFAULT 'monthly',
    alert_sent_at   INTEGER,  -- 存储 Unix 时间戳
    reset_at        INTEGER
);
