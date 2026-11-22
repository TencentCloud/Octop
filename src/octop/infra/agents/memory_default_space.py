"""专家「默认空间」推导：把 Octop 里某个专家的记忆库，映射成 octop-memory 的一个空间。

背景（2026-11-22 决定）：终端接入要回到「一条命令」的老形态，界面上不出现空间概念。
每个专家对应**一个默认空间**，且这个空间就是它原来那份记忆库 —— 不搬数据、不迁移。

关键约束（别自己发明推导逻辑）：octop-memory 服务端开库是

    Memory(namespace=space.space_id, backend=..., backend_config=space.backend_config)

也就是说 **namespace 必须等于 space_id**。而 Octop 自己开记忆库用的是
``open_memory_kwargs()``，命名空间固定为 ``agent_<agent_id>``。所以：

    space_id        = open_memory_kwargs(...)[0]          # agent_<agent_id>
    backend         = open_memory_kwargs(...)[1]          # sqlite / postgres
    backend_config  = open_memory_kwargs(...)[2]          # {"db_path": ...} 或 {"dsn": ...}

复用同一个函数推导，就不会出现「Octop 读 A 文件、memory 读 B 文件」这种静默错位。

R8（威胁模型）：如果那个 sqlite 文件里已经有表，但没有任何 ``<space_id>_`` 前缀的表，
说明命名空间对不上（历史遗留 / 手工改过），此时**不能**静默建一个空空间 —— 要报出来让人看。
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from octop.infra.agents.memory.backend import open_memory_kwargs


@dataclass(frozen=True)
class DefaultSpace:
    """专家的默认空间推导结果。"""

    space_id: str
    backend: str
    backend_config: dict[str, Any]
    db_path: str | None
    #: sqlite 文件里已有的表前缀；空列表表示文件是空的/还不存在（可以安全新建）
    known_prefixes: tuple[str, ...]
    #: 命名空间是否与该文件里已有的表对得上
    namespace_matches: bool
    #: 给面板直接展示的原因（不匹配或可新建时用）
    reason: str

    @property
    def usable(self) -> bool:
        """能否直接拿去建空间/签发 token。"""
        return self.namespace_matches


def _table_prefixes(db_path: Path) -> tuple[str, ...]:
    """读出 sqlite 里 ``<prefix>_atoms`` 这类表的前缀（只读，不建库）。"""
    if not db_path.exists():
        return ()
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return ()
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    except sqlite3.Error:
        return ()
    finally:
        conn.close()

    prefixes: set[str] = set()
    for (name,) in rows:
        if not isinstance(name, str):
            continue
        for suffix in ("_atoms", "_raw_events", "_entities"):
            if name.endswith(suffix):
                prefixes.add(name[: -len(suffix)])
                break
    return tuple(sorted(prefixes))


def default_space_for(
    *,
    agent_id: str,
    cfg: dict[str, Any],
    octop_config: Any,
    workspace_dir: Path,
) -> DefaultSpace:
    """推导某个专家的默认空间（与 Octop 自己开库的口径完全一致）。"""
    space_id, backend, backend_config = open_memory_kwargs(
        agent_id=agent_id,
        cfg=cfg,
        octop_config=octop_config,
        workspace_dir=workspace_dir,
    )
    db_path = (backend_config or {}).get("db_path") if backend == "sqlite" else None
    if backend != "sqlite":
        # PostgreSQL 下空间之间靠 schema/namespace 隔离，命名空间就是 space_id，
        # 不需要额外校验文件 —— 但要么是空的，要么对得上，交给服务端去开。
        return DefaultSpace(
            space_id=space_id,
            backend=backend,
            backend_config=dict(backend_config or {}),
            db_path=None,
            known_prefixes=(),
            namespace_matches=True,
            reason="postgres 后端：按 space_id 作为命名空间隔离",
        )

    path = Path(db_path).expanduser() if db_path else None
    if path is None:
        return DefaultSpace(
            space_id=space_id,
            backend=backend,
            backend_config=dict(backend_config or {}),
            db_path=None,
            known_prefixes=(),
            namespace_matches=False,
            reason="sqlite 但没解析出 db_path，拒绝自动建空间",
        )

    normalized = re.sub(r"[^a-z0-9_]", "_", space_id.lower())
    prefixes = _table_prefixes(path)
    if not prefixes:
        return DefaultSpace(
            space_id=space_id,
            backend=backend,
            backend_config=dict(backend_config or {}),
            db_path=str(path),
            known_prefixes=(),
            namespace_matches=True,
            reason="记忆库为空或还不存在：首次接入时会自动创建",
        )
    if normalized in prefixes:
        return DefaultSpace(
            space_id=space_id,
            backend=backend,
            backend_config=dict(backend_config or {}),
            db_path=str(path),
            known_prefixes=prefixes,
            namespace_matches=True,
            reason=f"命名空间对得上（{normalized}），直接复用原记忆库",
        )
    return DefaultSpace(
        space_id=space_id,
        backend=backend,
        backend_config=dict(backend_config or {}),
        db_path=str(path),
        known_prefixes=prefixes,
        namespace_matches=False,
        reason=(
            f"命名空间对不上：推导出的 space_id={normalized}，"
            f"但文件里已有 {', '.join(prefixes)} —— 不自动建空间，需要人工确认"
        ),
    )
