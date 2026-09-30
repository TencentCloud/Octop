"""Provider table access.

★ `api_key` 的**存储边界**（L 批）：写入经 `secret_codec.encrypt_value`（专用键 `providers_fernet`），
  读取在 `ProviderRow.from_row` 解密 ⇒ 调用方仍拿到明文（外部行为不变）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

import octop.infra.db.secret_codec as secret_codec
from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import (
    UNSET,
    DbRow,
    bool_int,
    insert_returning_id,
    now_ts,
)

if TYPE_CHECKING:
    from octop.infra.db.repos.agents import AgentRepo

_KEY_NAME = secret_codec.PROVIDERS_KEY
# ★ 老 SQLite 的变量上限（防撞）· ★ 批式回写每语句 ≤ `MAX_BATCH_ROWS` 行（本表为**单行** UPDATE）
MAX_SQLITE_VARIABLES = 999
MAX_BATCH_ROWS = 400

# ★ 静态 UPDATE 模板（L 批静态化 · 取代 f-string）：逐列 `CASE WHEN ? = 1 THEN col ELSE ? END`
#   · 每列 2 个参数 = `(1, None)`【未提供 ⇒ 保留旧值】/ `(0, <value>)`【提供 ⇒ 覆盖】
#   · ★ 严格保持 `partial_updates` 的「**None = skip**」旧语义（`repos/_base.py:34-39`）✓
#   · `updated_at` 恒更新（与旧行为一致）· ★ 参数 = 7 列 × 2 + 2 = 16 ≪ 999 ✓
_UPDATE_SQL = (
    "UPDATE providers SET "
    "kind = CASE WHEN ? = 1 THEN kind ELSE ? END, "
    "base_url = CASE WHEN ? = 1 THEN base_url ELSE ? END, "
    "api_key = CASE WHEN ? = 1 THEN api_key ELSE ? END, "
    "extra_json = CASE WHEN ? = 1 THEN extra_json ELSE ? END, "
    "models_json = CASE WHEN ? = 1 THEN models_json ELSE ? END, "
    "note = CASE WHEN ? = 1 THEN note ELSE ? END, "
    "enabled = CASE WHEN ? = 1 THEN enabled ELSE ? END, "
    "updated_at = ? WHERE id = ?"
)


def _flag(value: object | None) -> int:
    """★ 逐列「是否跳过」标志（N 批三态）：`UNSET`（未提供）⇒ `1`（`CASE` 保留旧值）；

    ★ 显式 `None`（清空）与任何非空值 ⇒ `0`（覆盖 · `None` ⇒ 写 NULL）。
    """
    return 1 if value is UNSET else 0


def _bindable(value: object | None) -> object | None:
    """★ `UNSET` ⇒ `None`：该列 `flag = 1` ⇒ 值被 `CASE` 忽略（★ `UNSET` 不可作 SQL 参数绑定）。"""
    return None if value is UNSET else value


@dataclass(frozen=True)
class ProviderRow:
    id: int
    name: str
    kind: str
    base_url: str | None
    api_key: str | None
    extra_json: str | None
    models_json: str | None
    note: str | None
    enabled: int
    created_at: int
    updated_at: int

    @classmethod
    def from_row(cls, r: DbRow, key: bytes | None = None) -> ProviderRow:
        """★ **解密落点**（F7）：`api_key` 在此解密 ⇒ 下游 79 个读点拿到明文。

        `key=None` ⇒ 不解密（★ 仅供迁移/自检等**明确知道**值形态的场景）；`api_key is None` ⇒ 透传。
        """
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
            base_url=r["base_url"],
            api_key=api_key,
            extra_json=r["extra_json"],
            models_json=r["models_json"],
            note=r["note"],
            enabled=r["enabled"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    def get_models(self) -> list[dict[str, object]]:
        """Return the models list from ``models_json``."""
        if self.models_json:
            try:
                data = json.loads(self.models_json)
                if isinstance(data, list):
                    return data
            except (json.JSONDecodeError, ValueError):
                pass
        return []


class ProviderRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db
        self._read_key: bytes | None = None
        self._write_key_cache: bytes | None = None

    def _key(self) -> bytes:
        """★ 读侧专用键：**只读解析**（缺键 ⇒ 抛错 · ★ 不生成 ⇒ 读路径无写入）。"""
        if self._read_key is None:
            self._read_key = secret_codec.resolve_key(self._db, _KEY_NAME)
        return self._read_key

    def _write_key(self) -> bytes:
        """★ 写侧专用键：缺失且无密文 ⇒ 自举；★ 有密文而缺键 ⇒ 抛错（拒绝静默换钥）。"""
        if self._write_key_cache is None:
            self._write_key_cache = secret_codec.ensure_key(self._db, _KEY_NAME)
        return self._write_key_cache

    def _row(self, r: DbRow | None) -> ProviderRow | None:
        if r is None:
            return None
        key = self._key() if r["api_key"] is not None else None
        return ProviderRow.from_row(r, key)

    def create(
        self,
        *,
        name: str,
        kind: str,
        base_url: str | None = None,
        api_key: str | None = None,
        extra_json: str | None = None,
        models_json: str | None = None,
        note: str | None = None,
    ) -> int:
        ts = now_ts()
        token = (
            secret_codec.encrypt_value(self._write_key(), api_key) if api_key is not None else None
        )
        with self._db.transaction() as conn:
            return insert_returning_id(
                conn,
                "INSERT INTO providers(name, kind, base_url, api_key, "
                "extra_json, models_json, note, enabled, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (name, kind, base_url, token, extra_json, models_json, note, ts, ts),
            )

    def get(self, provider_id: int) -> ProviderRow | None:
        with self._db.connect() as conn:
            r = conn.execute("SELECT * FROM providers WHERE id = ?", (provider_id,)).fetchone()
        return self._row(r)

    def get_by_name(self, name: str) -> ProviderRow | None:
        with self._db.connect() as conn:
            r = conn.execute("SELECT * FROM providers WHERE name = ?", (name,)).fetchone()
        return self._row(r)

    def list_all(self) -> list[ProviderRow]:
        with self._db.connect() as conn:
            rows = conn.execute("SELECT * FROM providers ORDER BY name").fetchall()
        return [row for row in (self._row(r) for r in rows) if row is not None]

    def update(
        self,
        provider_id: int,
        *,
        kind: str | None | object = UNSET,
        base_url: str | None | object = UNSET,
        api_key: str | None | object = UNSET,
        extra_json: str | None | object = UNSET,
        models_json: str | None | object = UNSET,
        note: str | None | object = UNSET,
        enabled: bool | None | object = UNSET,
    ) -> None:
        """★ **三态**（N 批 · 与 `repos/_base.py:optional_updates` 同族）：

        ★ 未提供（默认 `UNSET`）= **保留** · ★ 显式 `None` = **清空**（写 NULL）· ★ 非空 = **覆盖**。
        """
        if (
            kind is UNSET
            and base_url is UNSET
            and api_key is UNSET
            and extra_json is UNSET
            and models_json is UNSET
            and note is UNSET
            and enabled is UNSET
        ):
            # ★ 全列【未提供】⇒ 整条语句都不执行（含 `updated_at` 不变）·
            #   ★ 但显式 `None`（清空）**会**执行 ⇒ 三态与旧 `partial_updates` 的差别正在此处
            return
        token = (
            secret_codec.encrypt_value(self._write_key(), api_key)
            if isinstance(api_key, str)
            else None
        )
        # ★ 参数用【元组字面量】（★ 判据可逐位绑定值 ⇒ 桶② = 0）：每列 = (是否跳过, 值)
        params = (
            _flag(kind),
            _bindable(kind),
            _flag(base_url),
            _bindable(base_url),
            _flag(api_key),
            token,
            _flag(extra_json),
            _bindable(extra_json),
            _flag(models_json),
            _bindable(models_json),
            _flag(note),
            _bindable(note),
            _flag(enabled),
            bool_int(enabled) if isinstance(enabled, bool) else None,
            now_ts(),
            provider_id,
        )
        assert len(params) <= MAX_SQLITE_VARIABLES, "静态 UPDATE 参数超过老 SQLite 变量上限"
        with self._db.transaction() as conn:
            conn.execute(_UPDATE_SQL, params)

    def delete(self, provider_id: int) -> None:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))

    def find_referencing_agent_ids(self, agent_repo: AgentRepo, provider_name: str) -> list[str]:
        out: list[str] = []
        for row in agent_repo.list_all():
            cfg = json.loads(row.config_json or "{}")
            if provider_name in (cfg.get("providers") or []):
                out.append(row.agent_id)
        return out
