-- Track cumulative registrations and cap the number of uses per invite.
ALTER TABLE user_invites ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1;
ALTER TABLE user_invites ADD COLUMN max_uses INTEGER CHECK (max_uses > 0);
ALTER TABLE user_invites ADD COLUMN use_count INTEGER NOT NULL DEFAULT 0 CHECK (use_count >= 0);
UPDATE user_invites SET enabled = 0 WHERE used_at IS NOT NULL OR revoked_at IS NOT NULL;
UPDATE user_invites SET max_uses = 1;
UPDATE user_invites SET use_count = 1 WHERE used_at IS NOT NULL;
CREATE TABLE IF NOT EXISTS user_invite_redemptions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invite_id INTEGER NOT NULL REFERENCES user_invites(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  redeemed_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_invite_redemptions_invite ON user_invite_redemptions(invite_id, redeemed_at, id);
INSERT INTO user_invite_redemptions(invite_id, user_id, redeemed_at)
SELECT id, used_by_user_id, used_at FROM user_invites
WHERE used_by_user_id IS NOT NULL AND used_at IS NOT NULL
ON CONFLICT(user_id) DO NOTHING;
UPDATE _schema_version SET version = 26;
