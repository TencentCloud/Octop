"""Storage backend table access.

★ `access_key` / `secret_key` 的**存储边界**（L 批）：写入经 `secret_codec.encrypt_value`
  （专用键 `storage_fernet` —— ★ 与 `providers_fernet` **分域**，域轮换互不牵连），
  读取在 `BackendRow.from_row` 解密 ⇒ 调用方（对象存储 SDK 映射）仍拿到明文。
"""

from __future__ import annotations

from dataclasses import dataclass

import octop.infra.db.secret_codec as secret_codec
from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import (
    DbRow,
    bool_int,
    insert_returning_id,
    now_ts,
)

_KEY_NAME = secret_codec.STORAGE_KEY
MAX_SQLITE_VARIABLES = 999
MAX_BATCH_ROWS = 400

# ★ 静态 UPDATE 模板（L 批静态化 · 语义同 `repos/providers.py`）：9 列 + `enabled` ⇒ 10 列 × 2 + 2 = 22
_UPDATE_SQL = (
    "UPDATE storage_backends SET "
    "name = CASE WHEN ? = 1 THEN name ELSE ? END, "
    "kind = CASE WHEN ? = 1 THEN kind ELSE ? END, "
    "endpoint = CASE WHEN ? = 1 THEN endpoint ELSE ? END, "
    "access_key = CASE WHEN ? = 1 THEN access_key ELSE ? END, "
    "secret_key = CASE WHEN ? = 1 THEN secret_key ELSE ? END, "
    "bucket = CASE WHEN ? = 1 THEN bucket ELSE ? END, "
    "region = CASE WHEN ? = 1 THEN region ELSE ? END, "
    "config_json = CASE WHEN ? = 1 THEN config_json ELSE ? END, "
    "note = CASE WHEN ? = 1 THEN note ELSE ? END, "
    "enabled = CASE WHEN ? = 1 THEN enabled ELSE ? END, "
    "updated_at = ? WHERE id = ?"
)


def _flag(value: object | None) -> int:
    """★ 逐列「是否跳过」标志：`None` ⇒ `1`（`CASE` 保留旧值）；非空 ⇒ `0`（覆盖）。"""
    return 1 if value is None else 0


@dataclass(frozen=True)
class BackendRow:
    id: int
    name: str
    kind: str
    endpoint: str | None
    access_key: str | None
    secret_key: str | None
    bucket: str | None
    region: str | None
    config_json: str | None
    note: str | None
    enabled: int
    created_at: int
    updated_at: int

    @classmethod
    def from_row(cls, r: DbRow, key: bytes | None = None) -> BackendRow:
        """★ **解密落点**（F7）：`access_key` / `secret_key` 在此解密（`key=None` ⇒ 不解密）。"""
        raw_access, raw_secret = r["access_key"], r["secret_key"]
        if key is None:
            access_key, secret_key = raw_access, raw_secret
        else:
            access_key = (
                secret_codec.decrypt_value(key, raw_access) if raw_access is not None else None
            )
            secret_key = (
                secret_codec.decrypt_value(key, raw_secret) if raw_secret is not None else None
            )
        return cls(
            id=r["id"],
            name=r["name"],
            kind=r["kind"],
            endpoint=r["endpoint"],
            access_key=access_key,
            secret_key=secret_key,
            bucket=r["bucket"],
            region=r["region"],
            config_json=r["config_json"],
            note=r["note"],
            enabled=r["enabled"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )


class BackendRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db
        self._read_key: bytes | None = None
        self._write_key_cache: bytes | None = None

    def _key(self) -> bytes:
        """★ 读侧专用键：**只读解析**（缺键 ⇒ 抛错 · ★ 不生成）。"""
        if self._read_key is None:
            self._read_key = secret_codec.resolve_key(self._db, _KEY_NAME)
        return self._read_key

    def _write_key(self) -> bytes:
        """★ 写侧专用键：缺失且无密文 ⇒ 自举；★ 有密文而缺键 ⇒ 抛错。"""
        if self._write_key_cache is None:
            self._write_key_cache = secret_codec.ensure_key(self._db, _KEY_NAME)
        return self._write_key_cache

    def _row(self, r: DbRow | None) -> BackendRow | None:
        if r is None:
            return None
        has_secret = r["access_key"] is not None or r["secret_key"] is not None
        return BackendRow.from_row(r, self._key() if has_secret else None)

    def create(
        self,
        *,
        name: str,
        kind: str,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str | None = None,
        region: str | None = None,
        config_json: str | None = None,
        note: str | None = None,
    ) -> int:
        ts = now_ts()
        token_access = (
            secret_codec.encrypt_value(self._write_key(), access_key)
            if access_key is not None
            else None
        )
        token_secret = (
            secret_codec.encrypt_value(self._write_key(), secret_key)
            if secret_key is not None
            else None
        )
        with self._db.transaction() as conn:
            return insert_returning_id(
                conn,
                "INSERT INTO storage_backends"
                "(name, kind, endpoint, access_key, secret_key, bucket, region,"
                " config_json, note, enabled, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (
                    name,
                    kind,
                    endpoint,
                    token_access,
                    token_secret,
                    bucket,
                    region,
                    config_json,
                    note,
                    ts,
                    ts,
                ),
            )

    def get(self, backend_id: int) -> BackendRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM storage_backends WHERE id = ?", (backend_id,)
            ).fetchone()
        return self._row(r)

    def get_by_name(self, name: str) -> BackendRow | None:
        with self._db.connect() as conn:
            r = conn.execute("SELECT * FROM storage_backends WHERE name = ?", (name,)).fetchone()
        return self._row(r)

    def list_all(self) -> list[BackendRow]:
        with self._db.connect() as conn:
            rows = conn.execute("SELECT * FROM storage_backends ORDER BY name").fetchall()
        return [row for row in (self._row(r) for r in rows) if row is not None]

    def update(
        self,
        backend_id: int,
        *,
        name: str | None = None,
        kind: str | None = None,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str | None = None,
        region: str | None = None,
        config_json: str | None = None,
        note: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        if (
            name is None
            and kind is None
            and endpoint is None
            and access_key is None
            and secret_key is None
            and bucket is None
            and region is None
            and config_json is None
            and note is None
            and enabled is None
        ):
            # ★ 旧语义：全列未提供 ⇒ 不执行任何语句（`updated_at` 也不变）
            return
        token_access = (
            secret_codec.encrypt_value(self._write_key(), access_key)
            if access_key is not None
            else None
        )
        token_secret = (
            secret_codec.encrypt_value(self._write_key(), secret_key)
            if secret_key is not None
            else None
        )
        # ★ 参数用【元组字面量】（★ 判据可逐位绑定值 ⇒ 桶② = 0）：每列 = (是否跳过, 值)
        params = (
            _flag(name),
            name,
            _flag(kind),
            kind,
            _flag(endpoint),
            endpoint,
            _flag(access_key),
            token_access,
            _flag(secret_key),
            token_secret,
            _flag(bucket),
            bucket,
            _flag(region),
            region,
            _flag(config_json),
            config_json,
            _flag(note),
            note,
            _flag(enabled),
            bool_int(enabled) if enabled is not None else None,
            now_ts(),
            backend_id,
        )
        assert len(params) <= MAX_SQLITE_VARIABLES, "静态 UPDATE 参数超过老 SQLite 变量上限"
        with self._db.transaction() as conn:
            conn.execute(_UPDATE_SQL, params)

    def delete(self, backend_id: int) -> None:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM storage_backends WHERE id = ?", (backend_id,))
