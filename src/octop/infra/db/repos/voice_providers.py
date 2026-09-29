"""Voice provider table access.

★ `api_key` 的**存储边界**（L 批）：写入经 `secret_codec.encrypt_value`（专用键 `providers_fernet`
  —— 与 `providers` **同域**），读取在 `VoiceProviderRow.from_row` 解密 ⇒ 调用方仍拿到明文。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import octop.infra.db.secret_codec as secret_codec
from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import (
    DbRow,
    bool_int,
    insert_returning_id,
    now_ts,
)

_KEY_NAME = secret_codec.PROVIDERS_KEY
MAX_SQLITE_VARIABLES = 999
MAX_BATCH_ROWS = 400

# ★ 静态 UPDATE 模板（L 批静态化 · 语义同 `repos/providers.py`）：6 列 + `enabled` ⇒ 7 列 × 2 + 2 = 16
_UPDATE_SQL = (
    "UPDATE voice_providers SET "
    "kind = CASE WHEN ? = 1 THEN kind ELSE ? END, "
    "capability = CASE WHEN ? = 1 THEN capability ELSE ? END, "
    "base_url = CASE WHEN ? = 1 THEN base_url ELSE ? END, "
    "api_key = CASE WHEN ? = 1 THEN api_key ELSE ? END, "
    "extra_json = CASE WHEN ? = 1 THEN extra_json ELSE ? END, "
    "note = CASE WHEN ? = 1 THEN note ELSE ? END, "
    "enabled = CASE WHEN ? = 1 THEN enabled ELSE ? END, "
    "updated_at = ? WHERE id = ?"
)


def _flag(value: object | None) -> int:
    """★ 逐列「是否跳过」标志：`None` ⇒ `1`（`CASE` 保留旧值）；非空 ⇒ `0`（覆盖）。"""
    return 1 if value is None else 0


@dataclass(frozen=True)
class VoiceProviderRow:
    id: int
    name: str
    kind: str
    capability: str
    base_url: str | None
    api_key: str | None
    extra_json: str | None
    note: str | None
    enabled: int
    created_at: int
    updated_at: int

    @classmethod
    def from_row(cls, r: DbRow, key: bytes | None = None) -> VoiceProviderRow:
        """★ **解密落点**（F7）：`api_key` 在此解密（`key=None` ⇒ 不解密 · `None` 值透传）。"""
        raw_key = r["api_key"]
        api_key = (
            secret_codec.decrypt_value(key, raw_key)
            if key is not None and raw_key is not None
            else raw_key
        )
        return cls(
            id=r["id"],
            name=r["name"],
            kind=r["kind"],
            capability=r["capability"],
            base_url=r["base_url"],
            api_key=api_key,
            extra_json=r["extra_json"],
            note=r["note"],
            enabled=r["enabled"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    def get_extra(self) -> dict[str, Any]:
        if not self.extra_json:
            return {}
        try:
            data = json.loads(self.extra_json)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            pass
        return {}


class VoiceProviderRepo:
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

    def _row(self, r: DbRow | None) -> VoiceProviderRow | None:
        if r is None:
            return None
        key = self._key() if r["api_key"] is not None else None
        return VoiceProviderRow.from_row(r, key)

    def create(
        self,
        *,
        name: str,
        kind: str,
        capability: str,
        base_url: str | None = None,
        api_key: str | None = None,
        extra_json: str | None = None,
        note: str | None = None,
    ) -> int:
        ts = now_ts()
        token = (
            secret_codec.encrypt_value(self._write_key(), api_key) if api_key is not None else None
        )
        with self._db.transaction() as conn:
            return insert_returning_id(
                conn,
                "INSERT INTO voice_providers("
                "name, kind, capability, base_url, api_key, extra_json, note, "
                "enabled, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (name, kind, capability, base_url, token, extra_json, note, ts, ts),
            )

    def get(self, provider_id: int) -> VoiceProviderRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM voice_providers WHERE id = ?", (provider_id,)
            ).fetchone()
        return self._row(r)

    def get_by_name(self, name: str) -> VoiceProviderRow | None:
        with self._db.connect() as conn:
            r = conn.execute("SELECT * FROM voice_providers WHERE name = ?", (name,)).fetchone()
        return self._row(r)

    def list_all(self) -> list[VoiceProviderRow]:
        with self._db.connect() as conn:
            rows = conn.execute("SELECT * FROM voice_providers ORDER BY name").fetchall()
        return [row for row in (self._row(r) for r in rows) if row is not None]

    def update(
        self,
        provider_id: int,
        *,
        kind: str | None = None,
        capability: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        extra_json: str | None = None,
        note: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        if (
            kind is None
            and capability is None
            and base_url is None
            and api_key is None
            and extra_json is None
            and note is None
            and enabled is None
        ):
            # ★ 旧语义：全列未提供 ⇒ 不执行任何语句（`updated_at` 也不变）
            return
        token = (
            secret_codec.encrypt_value(self._write_key(), api_key) if api_key is not None else None
        )
        # ★ 参数用【元组字面量】（★ 判据可逐位绑定值 ⇒ 桶② = 0）：每列 = (是否跳过, 值)
        params = (
            _flag(kind),
            kind,
            _flag(capability),
            capability,
            _flag(base_url),
            base_url,
            _flag(api_key),
            token,
            _flag(extra_json),
            extra_json,
            _flag(note),
            note,
            _flag(enabled),
            bool_int(enabled) if enabled is not None else None,
            now_ts(),
            provider_id,
        )
        assert len(params) <= MAX_SQLITE_VARIABLES, "静态 UPDATE 参数超过老 SQLite 变量上限"
        with self._db.transaction() as conn:
            conn.execute(_UPDATE_SQL, params)

    def delete(self, provider_id: int) -> None:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM voice_providers WHERE id = ?", (provider_id,))
