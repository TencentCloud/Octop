"""Published expert templates — one row per user-published expert."""

from __future__ import annotations

from dataclasses import dataclass

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, map_rows, now_ts


@dataclass(frozen=True)
class PublishedExpertRow:
    id: str
    slug: str
    name: str
    description: str
    created_by: str
    source_agent_id: str | None
    icon_name: str
    color: str
    created_at: int
    updated_at: int

    @classmethod
    def from_row(cls, r: DbRow) -> PublishedExpertRow:
        return cls(
            id=r["id"],
            slug=r["slug"],
            name=r["name"],
            description=r["description"],
            created_by=r["created_by"],
            source_agent_id=r["source_agent_id"],
            icon_name=r["icon_name"],
            color=r["color"],
            created_at=int(r["created_at"]),
            updated_at=int(r["updated_at"]),
        )


class PublishedExpertRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def list_all(self) -> list[PublishedExpertRow]:
        with self._db.connect() as conn:
            rows = conn.execute("SELECT * FROM published_experts ORDER BY name").fetchall()
        return map_rows(rows, PublishedExpertRow)

    def get(self, expert_id: str) -> PublishedExpertRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM published_experts WHERE id = ?",
                (expert_id,),
            ).fetchone()
        return PublishedExpertRow.from_row(r) if r else None

    def get_by_slug(self, slug: str) -> PublishedExpertRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM published_experts WHERE slug = ?",
                (slug,),
            ).fetchone()
        return PublishedExpertRow.from_row(r) if r else None

    def get_by_source_agent_id(self, source_agent_id: str) -> PublishedExpertRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM published_experts WHERE source_agent_id = ? ORDER BY created_at LIMIT 1",
                (source_agent_id,),
            ).fetchone()
        return PublishedExpertRow.from_row(r) if r else None

    def create(
        self,
        *,
        id: str,
        slug: str,
        name: str,
        description: str = "",
        created_by: str,
        source_agent_id: str | None = None,
        icon_name: str = "",
        color: str = "",
    ) -> PublishedExpertRow:
        ts = now_ts()
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO published_experts("
                "id, slug, name, description, created_by, source_agent_id, "
                "icon_name, color, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    id,
                    slug,
                    name,
                    description,
                    created_by,
                    source_agent_id,
                    icon_name,
                    color,
                    ts,
                    ts,
                ),
            )
        row = self.get(id)
        if row is None:
            raise RuntimeError(f"published expert insert failed: {id}")
        return row

    def update_snapshot_meta(
        self,
        expert_id: str,
        *,
        icon_name: str | None = None,
        color: str | None = None,
        description: str | None = None,
        name: str | None = None,
    ) -> PublishedExpertRow:
        """Refresh listing metadata and bump ``updated_at`` after a snapshot rewrite."""
        fields: list[str] = ["updated_at = ?"]
        values: list[object] = [now_ts()]
        if icon_name is not None:
            fields.append("icon_name = ?")
            values.append(icon_name)
        if color is not None:
            fields.append("color = ?")
            values.append(color)
        if description is not None:
            fields.append("description = ?")
            values.append(description)
        if name is not None:
            fields.append("name = ?")
            values.append(name)
        values.append(expert_id)
        with self._db.transaction() as conn:
            conn.execute(
                f"UPDATE published_experts SET {', '.join(fields)} WHERE id = ?",
                tuple(values),
            )
        row = self.get(expert_id)
        if row is None:
            raise RuntimeError(f"published expert update failed: {expert_id}")
        return row

    def delete(self, expert_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM published_experts WHERE id = ?", (expert_id,))
