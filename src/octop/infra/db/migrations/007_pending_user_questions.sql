CREATE TABLE pending_user_questions (
    pending_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    session_key TEXT NOT NULL,
    channel_type TEXT NOT NULL,
    questions_json TEXT NOT NULL,
    answer_json TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'resuming', 'answered', 'cancelled')),
    created_at INTEGER NOT NULL,
    answered_at INTEGER
);

CREATE INDEX idx_pending_user_questions_thread
    ON pending_user_questions(thread_id, agent_id, user_id, status, created_at DESC);

CREATE INDEX idx_pending_user_questions_session
    ON pending_user_questions(session_key, agent_id, status, created_at DESC);

UPDATE _schema_version SET version = 7;
