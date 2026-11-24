"""Department (group) token quota management."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from octop.infra.db.pool import DatabasePool

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GroupQuota:
    group_id: int
    quota_tokens: int
    used_tokens: int
    alert_threshold: float
    period: str
    alert_sent_at: datetime | None


class GroupQuotaRepo:
    def __init__(self, db: DatabasePool):
        self._db = db

    def resolve_primary_group(self, user_id: int) -> int | None:
        """取用户的主组（部门）；没有主组则取最早加入的组。"""
        with self._db.connect() as conn:
            try:
                row = conn.execute(
                    """
                    SELECT g.id
                    FROM user_group_member m
                    JOIN user_group g ON g.user_group_id = m.user_group_id
                    WHERE m.user_id = ? AND g.enabled = 1
                    ORDER BY m.created_at ASC
                    LIMIT 1
                    """,
                    (user_id,),
                ).fetchone()
            except Exception as e:
                logger.warning("resolve_primary_group failed: %s", e, exc_info=True)
                return None

        if not row:
            return None
        return int(row[0])

    def get(self, group_id: int) -> GroupQuota | None:
        """获取部门的当前配额状态。"""
        with self._db.connect() as conn:
            row = conn.execute(
                """
                SELECT group_id, quota_tokens, used_tokens, alert_threshold, period, alert_sent_at
                FROM group_quotas
                WHERE group_id = ?
                """,
                (group_id,),
            ).fetchone()

        if not row:
            return None

        # 假设数据库返回的 alert_sent_at 是 Unix 时间戳 (int) 或者字符串，这里做个兼容处理
        alert_sent = row["alert_sent_at"]
        if isinstance(alert_sent, (int, float)):
            alert_sent = datetime.fromtimestamp(alert_sent, tz=UTC)

        return GroupQuota(
            group_id=int(row["group_id"]),
            quota_tokens=int(row["quota_tokens"]),
            used_tokens=int(row["used_tokens"]),
            alert_threshold=float(row["alert_threshold"]),
            period=str(row["period"]),
            alert_sent_at=alert_sent,
        )

    def increment_used(self, group_id: int, delta: int) -> None:
        """原子增加部门已用 Token 数。

        注意：必须使用 UPDATE ... SET used = used + ?，不能先查后写，防止并发穿透。
        """
        if delta <= 0:
            return

        with self._db.connect() as conn:
            # 1. 原子累加用量
            conn.execute(
                """
                UPDATE group_quotas
                SET used_tokens = used_tokens + ?
                WHERE group_id = ?
                """,
                (delta, group_id),
            )

            # 2. 检查是否触发预警（复用同一次数据库连接，减少开销）
            self._maybe_trigger_alert(conn, group_id, delta)

    def _maybe_trigger_alert(self, conn: Any, group_id: int, delta: int) -> None:
        """如果达到预警阈值，且本周期内未发送过，则触发预警。"""
        row = conn.execute(
            """
            SELECT quota_tokens, used_tokens, alert_threshold, alert_sent_at
            FROM group_quotas
            WHERE group_id = ?
            """,
            (group_id,),
        ).fetchone()

        if not row:
            return

        quota_tokens = int(row["quota_tokens"])
        used_tokens = int(row["used_tokens"])
        threshold = float(row["alert_threshold"])

        if quota_tokens <= 0:
            return

        # 未达到阈值，直接返回
        if used_tokens < quota_tokens * threshold:
            return

        # 已经触发过预警（且未重置），直接返回
        if row["alert_sent_at"] is not None:
            return

        # 标记为已预警（写入当前时间戳）
        conn.execute(
            "UPDATE group_quotas SET alert_sent_at = ? WHERE group_id = ?",
            (int(datetime.now(UTC).timestamp()), group_id),
        )

        # TODO: 在这里调用你的通知系统（Webhook/飞书/邮件）
        logger.warning(
            "【部门配额预警】部门 %s 的 Token 用量已达到 %.2f%% (%s/%s)",
            group_id,
            (used_tokens / quota_tokens) * 100,
            used_tokens,
            quota_tokens,
        )

        # 示例：
        # import asyncio
        # from your_notify_module import send_alert
        # asyncio.create_task(send_alert(f"部门 {group_id} 配额即将耗尽"))

    def set_quota(
        self,
        group_id: int,
        quota_tokens: int,
        alert_threshold: float = 0.8,
        period: str = "monthly",
    ) -> None:
        """创建或更新部门配额（供管理后台调用）。"""
        with self._db.connect() as conn:
            # 使用 UPSERT (SQLite 和 PostgreSQL 均支持 ON CONFLICT 语法)
            conn.execute(
                """
                INSERT INTO group_quotas (group_id, quota_tokens, used_tokens, alert_threshold, period)
                VALUES (?, ?, 0, ?, ?)
                ON CONFLICT(group_id) DO UPDATE SET
                    quota_tokens = excluded.quota_tokens,
                    alert_threshold = excluded.alert_threshold,
                    period = excluded.period
                """,
                (group_id, quota_tokens, alert_threshold, period),
            )
