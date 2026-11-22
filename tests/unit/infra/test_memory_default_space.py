"""专家默认空间推导的单测。

要证明的三件事：
1. 推导出来的 space_id 与 Octop 自己开记忆库的命名空间**完全一致**（都是 ``agent_<id>``）；
2. 记忆库为空/不存在时，允许首次接入自动建空间；
3. 记忆库里已有表、但命名空间对不上时，**必须报出来**而不是静默建空空间（威胁模型 R8）。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from octop.infra.agents import memory_default_space as mod


def _make_db(path: Path, prefixes: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        for prefix in prefixes:
            for suffix in ("_atoms", "_raw_events", "_entities"):
                conn.execute(f"CREATE TABLE {prefix}{suffix} (id INTEGER PRIMARY KEY)")
        conn.commit()
    finally:
        conn.close()
    return path


def _cfg() -> dict:
    return {"memory": {"backend": {"type": "sqlite"}}}


def _octop_config() -> SimpleNamespace:
    return SimpleNamespace(database=SimpleNamespace(is_postgresql=False))


def test_space_id_matches_octop_namespace(tmp_path: Path) -> None:
    db = _make_db(tmp_path / "memory.sqlite", ["agent_abc"])

    space = mod.default_space_for(
        agent_id="abc",
        cfg=_cfg(),
        octop_config=_octop_config(),
        workspace_dir=tmp_path,
    )

    assert space.space_id == "agent_abc"
    assert space.backend == "sqlite"
    assert space.db_path == str(db)
    assert space.namespace_matches is True
    assert space.usable is True
    assert "agent_abc" in space.reason


def test_missing_db_allows_first_setup(tmp_path: Path) -> None:
    space = mod.default_space_for(
        agent_id="fresh",
        cfg=_cfg(),
        octop_config=_octop_config(),
        workspace_dir=tmp_path,
    )

    assert space.space_id == "agent_fresh"
    assert space.known_prefixes == ()
    assert space.namespace_matches is True
    assert "自动创建" in space.reason


def test_namespace_mismatch_is_refused(tmp_path: Path) -> None:
    _make_db(tmp_path / "memory.sqlite", ["agent_someone_else"])

    space = mod.default_space_for(
        agent_id="abc",
        cfg=_cfg(),
        octop_config=_octop_config(),
        workspace_dir=tmp_path,
    )

    assert space.namespace_matches is False
    assert space.usable is False
    assert "agent_someone_else" in space.reason
    assert "人工确认" in space.reason


def test_empty_tables_still_count_as_empty(tmp_path: Path) -> None:
    # 建了表但一行数据都没有，也算可用（历史空壳库）
    _make_db(tmp_path / "memory.sqlite", ["agent_abc"])

    space = mod.default_space_for(
        agent_id="abc",
        cfg=_cfg(),
        octop_config=_octop_config(),
        workspace_dir=tmp_path,
    )

    assert space.namespace_matches is True


@pytest.mark.parametrize("agent_id", ["6TK96K", "Z026BY"])
def test_ids_with_mixed_case_keep_identity(tmp_path: Path, agent_id: str) -> None:
    # 命名空间不做大小写变换：agent_id 是什么，space_id 就是什么，
    # 否则会和 Octop 自己开库时用的 namespace 对不上。
    _make_db(tmp_path / "memory.sqlite", [f"agent_{agent_id}"])

    space = mod.default_space_for(
        agent_id=agent_id,
        cfg=_cfg(),
        octop_config=_octop_config(),
        workspace_dir=tmp_path,
    )

    assert space.space_id == f"agent_{agent_id}"
    assert space.namespace_matches is True
