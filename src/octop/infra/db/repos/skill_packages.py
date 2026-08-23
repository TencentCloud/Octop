"""Skill package metadata — one row per global skill package."""

from __future__ import annotations

from dataclasses import dataclass

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, map_rows, now_ts, partial_updates


@dataclass(frozen=True)
class SkillPackageRow:
    id: str
    pk: int
    name: str
    description: str
    created_by: str
    skill_count: int
    icon_name: str
    icon_url: str
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, r: DbRow) -> SkillPackageRow:
        # sqlite3.Row's ``in`` checks values, not column names — use ``.keys()``.
        keys = frozenset(r.keys()) if hasattr(r, "keys") else frozenset()
        return cls(
            id=str(r["skill_package_id"]),
            pk=int(r["id"]),
            name=r["name"],
            description=r["description"],
            created_by=r["created_by"],
            skill_count=r["skill_count"],
            icon_name=str(r["icon_name"]) if "icon_name" in keys else "",
            icon_url=str(r["icon_url"]) if "icon_url" in keys else "",
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )


class SkillPackageRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def list_all(self) -> list[SkillPackageRow]:
        with self._db.connect() as conn:
            rows = conn.execute("SELECT * FROM skill_packages ORDER BY name").fetchall()
        return map_rows(rows, SkillPackageRow)

    def get(self, package_id: str) -> SkillPackageRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM skill_packages WHERE skill_package_id = ?",
                (package_id,),
            ).fetchone()
        return SkillPackageRow.from_row(r) if r else None

    def get_by_name(self, name: str) -> SkillPackageRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM skill_packages WHERE name = ?",
                (name,),
            ).fetchone()
        return SkillPackageRow.from_row(r) if r else None

    def create(
        self,
        *,
        id: str,
        name: str,
        description: str = "",
        created_by: str,
        icon_name: str = "",
        icon_url: str = "",
    ) -> SkillPackageRow:
        ts = str(now_ts())
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO skill_packages("
                "skill_package_id, name, description, created_by, skill_count, "
                "icon_name, icon_url, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?)",
                (id, name, description, created_by, icon_name, icon_url, ts, ts),
            )
        row = self.get(id)
        if row is None:
            raise RuntimeError(f"skill package insert failed: {id}")
        return row

    def update(
        self,
        package_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        icon_name: str | None = None,
        icon_url: str | None = None,
    ) -> None:
        fields, params = partial_updates(
            [
                ("name", name),
                ("description", description),
                ("icon_name", icon_name),
                ("icon_url", icon_url),
            ]
        )
        if not fields:
            return
        fields.append("updated_at = ?")
        params.append(str(now_ts()))
        params.append(package_id)
        with self._db.transaction() as conn:
            conn.execute(
                f"UPDATE skill_packages SET {', '.join(fields)} WHERE skill_package_id = ?",
                params,
            )

    def delete(self, package_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "DELETE FROM skill_packages WHERE skill_package_id = ?",
                (package_id,),
            )

    def update_skill_count(self, package_id: str, count: int) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE skill_packages SET skill_count = ?, updated_at = ? "
                "WHERE skill_package_id = ?",
                (count, str(now_ts()), package_id),
            )
