"""Uploaded portraits stored in the control-plane database."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import now_ts


def _as_bytes(value: Any) -> bytes:
    if isinstance(value, memoryview):
        return value.tobytes()
    return bytes(value)


@dataclass(frozen=True)
class ProfileAvatar:
    media_type: str
    content: bytes
    updated_at: int


class ProfileAvatarRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def get(self, owner_kind: str, owner_id: str) -> ProfileAvatar | None:
        with self._db.connect() as conn:
            row = conn.execute(
                """
                SELECT media_type, content, updated_at
                FROM profile_avatars
                WHERE owner_kind = ? AND owner_id = ?
                """,
                (owner_kind, owner_id),
            ).fetchone()
        if row is None:
            return None
        return ProfileAvatar(
            media_type=str(row["media_type"]),
            content=_as_bytes(row["content"]),
            updated_at=int(row["updated_at"]),
        )

    def put(self, owner_kind: str, owner_id: str, content: bytes, media_type: str) -> int:
        updated_at = now_ts()
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO profile_avatars(owner_kind, owner_id, media_type, content, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(owner_kind, owner_id) DO UPDATE SET
                  media_type = excluded.media_type,
                  content = excluded.content,
                  updated_at = excluded.updated_at
                """,
                (owner_kind, owner_id, media_type, content, updated_at),
            )
        return updated_at

    def delete(self, owner_kind: str, owner_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "DELETE FROM profile_avatars WHERE owner_kind = ? AND owner_id = ?",
                (owner_kind, owner_id),
            )
