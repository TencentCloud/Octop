"""T-57 —— ``portable/adopt`` 的目标文件：新布局 vs legacy。

缺陷：``octop_memory · adopter.py · _resolve_target_db_path`` 对 ``host_kind="agent"``
推出的是 **legacy** 路径 ``~/.octop/agents/{id}/memory.sqlite``，而新布局 agent 真正读的是
``{workspace}/.octop/memory.sqlite``（``memory_client.memory_db_path_for_cfg`` →
``host_system_dir``）⇒ 不覆盖 ``target_db_path`` 就等于"迁了个寂寞"。

本文件断言三件事：① 路由把**唯一真源**算出的路径喂给 ``adopt()``（不是照抄字符串）；
② 两条端到端 —— 新布局与 legacy **都能在该 agent 会读的路径上读到刚迁入的记忆**；
③ 正对照 —— 外部宿主与"不指定"时仍是既有行为；作用域拒绝时一个文件都不碰。

安全语义（AUD-1/AUD-2）不在这里重测：判定函数全部复用
``tests/unit/agents/test_memory_portable_scope.py`` 所覆盖的 T-56 实现。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from octop.api.common.memory_client import memory_db_path_for_cfg
from octop.api.routers import memory_portable as mp
from octop.infra.agents.memory.portable import namespace_scope as ns
from octop.infra.errors import ErrorCode, OctopError

AGENT_ID = "a1"
SENTINEL = "T57-SENTINEL-迁移可用"

NEW_LAYOUT_CFG: dict[str, Any] = {"system_files_path": ".octop"}
LEGACY_CFG: dict[str, Any] = {}


def _user(*, uid: int = 1) -> Any:
    return SimpleNamespace(id=uid, is_admin=False)


class _Row:
    def __init__(self, cfg: dict[str, Any]) -> None:
        self.agent_id = AGENT_ID
        self.user_id = 1
        self.is_shared = 0
        self.config_json = json.dumps(cfg)


def _server(workspace: Path, cfg: dict[str, Any]) -> Any:
    """最小 server：所有权检查与工作区/cfg 解析所需的三个面。"""
    row = _Row(cfg)
    registry = SimpleNamespace(
        get_row=lambda agent_id: row if agent_id == AGENT_ID else None,
        resolve_workspace_dir=lambda agent_id: workspace,
    )
    return SimpleNamespace(
        app_runtime=SimpleNamespace(agent_registry=registry),
        services=SimpleNamespace(agent_repo=SimpleNamespace(get=lambda agent_id: row)),
    )


class _PkgFile:
    def __init__(self, payload: bytes = b"not-a-real-package") -> None:
        self._payload = payload

    async def read(self) -> bytes:
        return self._payload


class _AdoptSpy:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, pkg_path: Any, target_host: str, **kwargs: Any) -> Any:
        self.calls.append({"target_host": target_host, **kwargs})
        return SimpleNamespace(to_dict=lambda: {"target_namespace": kwargs.get("target_namespace")})


@pytest.fixture
def adopt_env(monkeypatch: pytest.MonkeyPatch) -> _AdoptSpy:
    """替身：postgres 拒绝检查 + 包内 manifest 读取（路由里两个重活）。"""
    import octop_memory.operations.migration.portable as portable_pkg

    spy = _AdoptSpy()
    monkeypatch.setattr(portable_pkg, "adopt", spy)
    monkeypatch.setattr(mp, "_refuse_postgres_portable", lambda *_a, **_k: None)
    monkeypatch.setattr(mp, "_read_manifest_or_value_error", lambda _path: {"agent_name": AGENT_ID})
    return spy


async def _adopt(server: Any, **overrides: Any) -> Any:
    kwargs: dict[str, Any] = {
        "agent_id": AGENT_ID,
        "pkg_file": _PkgFile(),
        "target_host": "agent",
        "target_namespace": None,
        "on_conflict": "skip",
        "host_rewrite": "keep",
        "dry_run": False,
        "user": _user(),
        "server": server,
        "as_user": None,
    }
    kwargs.update(overrides)
    return await mp.adopt_agent_memory(**kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# 目标路径来自唯一真源（不是第二份拼法）
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("cfg", "suffix"),
    [
        (NEW_LAYOUT_CFG, Path(".octop") / "memory.sqlite"),
        (LEGACY_CFG, Path("memory.sqlite")),
    ],
)
def test_target_path_comes_from_the_one_resolver(
    tmp_path: Path, cfg: dict[str, Any], suffix: Path
) -> None:
    """断言对的是**真源算出的期望值**，不是写死的 ``.octop/memory.sqlite`` 字符串。"""
    server = _server(tmp_path, cfg)

    assert mp._agent_memory_db_path(server, AGENT_ID) == memory_db_path_for_cfg(tmp_path, cfg)
    assert mp._agent_memory_db_path(server, AGENT_ID) == tmp_path / suffix


async def test_route_hands_the_resolved_path_to_adopt(adopt_env: _AdoptSpy, tmp_path: Path) -> None:
    """① 新布局：路由必须显式传 ``target_db_path``，否则 adopt 写 legacy。"""
    server = _server(tmp_path, NEW_LAYOUT_CFG)

    assert (await _adopt(server)).status_code == 200

    assert adopt_env.calls[0]["target_db_path"] == memory_db_path_for_cfg(tmp_path, NEW_LAYOUT_CFG)
    assert adopt_env.calls[0]["target_db_path"] == tmp_path / ".octop" / "memory.sqlite"


async def test_route_hands_the_legacy_path_for_a_legacy_agent(
    adopt_env: _AdoptSpy, tmp_path: Path
) -> None:
    """② legacy：同一个解析器直接给出 ``{workspace}/memory.sqlite``，无需特判。"""
    server = _server(tmp_path, LEGACY_CFG)

    await _adopt(server)

    assert adopt_env.calls[0]["target_db_path"] == tmp_path / "memory.sqlite"


@pytest.mark.parametrize("host", ["openclaw", "hermes", "octopmemory", "openclaw:openclaw__a1"])
async def test_external_hosts_keep_the_library_resolution(
    adopt_env: _AdoptSpy, tmp_path: Path, host: str
) -> None:
    """③ 正对照：外部宿主的目标文件不归 Octop 管 ⇒ 不传覆盖，既有行为逐字不变。"""
    server = _server(tmp_path, NEW_LAYOUT_CFG)

    await _adopt(server, target_host=host)

    assert adopt_env.calls[0]["target_db_path"] is None


# ─────────────────────────────────────────────────────────────────────────────
# 端到端：真的迁进去，且在该 agent 会读的路径上真的读得出来
# ─────────────────────────────────────────────────────────────────────────────


def _make_package(directory: Path, namespace: str = "agent_a1") -> Path:
    """用真 packer 造一个含 raw_event + atom 的 ``.hmpkg``。"""
    from octop_memory.core import Memory
    from octop_memory.operations.migration.portable import pack
    from octop_memory.operations.migration.portable.models import SourceInfo
    from octop_memory.types import AtomCard

    source_db = directory / ".octop" / "memory.sqlite"
    source_db.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    memory = Memory(
        namespace=namespace, backend="sqlite", backend_config={"db_path": str(source_db)}
    )
    memory.add_raw(SENTINEL, event_type="user_message", host="octop")
    memory.add_atom(
        AtomCard(
            id="atom-t57",
            entity_id="ent-1",
            candidate_id="cand-1",
            raw_event_ids=[],
            assertion=SENTINEL,
            verbatim_quote=SENTINEL,
            quote_event_id="",
            search_terms=["t57"],
            occurred_at=now,
            confidence="high",
            importance="high",
            created_at=now,
        )
    )
    package = directory / "a1.hmpkg"
    pack(
        SourceInfo(
            host_kind="agent", db_path=str(source_db), namespace=namespace, agent_name=AGENT_ID
        ),
        out=package,
    )
    return package


def _read_back(target: Path, namespace: str = "agent_a1") -> tuple[list[str], list[str]]:
    """从目标文件读回 (atom 断言, raw 正文) —— 「迁了个寂寞」的判据。"""
    from octop_memory.core import Memory

    memory = Memory(namespace=namespace, backend="sqlite", backend_config={"db_path": str(target)})
    return (
        [atom.assertion for atom in memory.list_atoms(limit=10)],
        [event.content for event in memory.list_raw(limit=10)],
    )


async def test_new_layout_adopt_is_readable_at_the_resolved_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """① 端到端：新布局 agent ⇒ 迁入的记忆在 ``{workspace}/.octop/memory.sqlite`` 上读得出来。"""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(mp, "_refuse_postgres_portable", lambda *_a, **_k: None)
    workspace = tmp_path / "agents" / AGENT_ID
    package = _make_package(tmp_path / "src")
    server = _server(workspace, NEW_LAYOUT_CFG)

    response = await _adopt(
        server,
        pkg_file=_PkgFile(package.read_bytes()),
        target_namespace=ns.allowed_agent_namespace(AGENT_ID),
        on_conflict="replace",
    )

    assert response.status_code == 200
    target = memory_db_path_for_cfg(workspace, NEW_LAYOUT_CFG)
    assert target == workspace / ".octop" / "memory.sqlite"
    assert target.is_file(), "target_db_path 必须真的落在这个文件上"
    assert _read_back(target) == ([SENTINEL], [SENTINEL])

    legacy = Path("~/.octop/agents").expanduser() / AGENT_ID / "memory.sqlite"
    assert not legacy.exists(), "不得再顺手往 legacy 路径写一份"


async def test_legacy_layout_adopt_is_readable_at_the_resolved_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """② 端到端：legacy agent（cfg 无 ``system_files_path``）同样读得出来。"""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(mp, "_refuse_postgres_portable", lambda *_a, **_k: None)
    workspace = tmp_path / "agents" / AGENT_ID
    package = _make_package(tmp_path / "src")
    server = _server(workspace, LEGACY_CFG)

    response = await _adopt(
        server,
        pkg_file=_PkgFile(package.read_bytes()),
        target_namespace=ns.allowed_agent_namespace(AGENT_ID),
        on_conflict="replace",
    )

    assert response.status_code == 200
    target = memory_db_path_for_cfg(workspace, LEGACY_CFG)
    assert target == workspace / "memory.sqlite"
    assert _read_back(target) == ([SENTINEL], [SENTINEL])


async def test_new_layout_adopt_without_the_override_would_miss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """缺陷本体（对照组，不经过路由）：adopt 自己推的是 legacy 路径。

    这条用例把"为什么必须覆盖"钉成可失败事实：同一个包、同一个目标 agent，
    **不传** ``target_db_path`` 时记忆落在 ``~/.octop/agents/{id}/memory.sqlite`` ——
    而路由（上一条用例）现在落在真源路径上，两者不是同一个文件。
    """
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    from octop_memory.operations.migration.portable import adopt

    package = _make_package(tmp_path / "src")
    adopt(package, "agent", target_namespace="agent_a1", on_conflict="replace")

    library_default = Path("~/.octop/agents").expanduser() / AGENT_ID / "memory.sqlite"
    assert library_default.is_file(), "第三方默认行为未变（这也是 ③ 正对照的一半）"
    workspace_target = memory_db_path_for_cfg(tmp_path / "agents" / AGENT_ID, NEW_LAYOUT_CFG)
    assert not workspace_target.exists(), "默认路径与 agent 真正读的路径不是同一个文件"


async def test_rejected_scope_never_reaches_the_target_file(
    adopt_env: _AdoptSpy, tmp_path: Path
) -> None:
    """④ 安全语义不回退：作用域拒绝发生在算路径/写盘之前，目标文件一个都不建。"""
    server = _server(tmp_path, NEW_LAYOUT_CFG)

    with pytest.raises(OctopError) as excinfo:
        await _adopt(server, target_namespace="project_P1")

    assert excinfo.value.code == ErrorCode.FORBIDDEN
    assert excinfo.value.status == 403
    assert adopt_env.calls == [], "拒绝必须发生在 adopt() 之前"
    assert not (tmp_path / ".octop" / "memory.sqlite").exists()
