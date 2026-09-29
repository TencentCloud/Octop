"""portable 记忆迁移的命名空间作用域（AUD-1 / AUD-2）。

两个**已发布**端点的安全回归：

* ``POST /api/agents/{agent_id}/memory/portable/adopt`` —— 设计四条写入路径之外的**第 5 条**。
* ``GET  /api/memory/portable/sources`` —— 主机级 store 枚举。

只测**判定**（纯函数 + 路由的纯 helper）与**路由的调用契约**
（拒绝时 ``adopt()`` 一次都不许被调用），不依赖数据库、不真写盘。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from octop.api.routers import memory_portable as mp
from octop.infra.agents.memory.portable import namespace_scope as ns
from octop.infra.errors import ErrorCode, OctopError

AGENT_ID = "a1"


# ── 纯函数：格式门 ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "namespace",
    ["agent_a1", "project_P1", "team_T1", "agent_a1_", "openclaw__a1", "a.b-c_1"],
)
def test_well_formed_namespaces(namespace: str) -> None:
    assert ns.namespace_is_well_formed(namespace) is True


@pytest.mark.parametrize(
    "namespace",
    [
        "",
        " ",
        "..",
        "../../etc",
        "a/../b",
        "a/b",
        "a\\b",
        "/abs",
        "C:\\x",
        "-leading-dash",
        ".hidden",
        "x" * (ns.MAX_NAMESPACE_LEN + 1),
    ],
)
def test_malformed_namespaces_are_rejected(namespace: str) -> None:
    """路径分隔符 / ``..`` / 绝对路径 / 盘符 / 超长 一律不合法（`mkdir(parents=True)` 的上游）。"""
    assert ns.namespace_is_well_formed(namespace) is False


def test_split_host_spec_matches_the_adopter_semantics() -> None:
    """`host:namespace` 的解析必须与 `octop_memory …/adopter.py @208-213` **同语义**。"""
    assert ns.split_host_spec("agent") == ("agent", None)
    assert ns.split_host_spec("agent:project_P1") == ("agent", "project_P1")
    assert ns.split_host_spec("AGENT") == ("agent", None)
    assert ns.split_host_spec("  agent  ") == ("agent", None)
    assert ns.split_host_spec("openclaw:openclaw__a1") == ("openclaw", "openclaw__a1")


def test_own_namespace_comes_from_the_single_authority() -> None:
    """命名空间拼法**不得**在本模块另写一份（真源 = `memory/backend.py · agent_memory_namespace`）。"""
    from octop.infra.agents.memory.backend import agent_memory_namespace

    assert ns.allowed_agent_namespace(AGENT_ID) == agent_memory_namespace(AGENT_ID)


# ── 纯函数：跨命名空间必须被拒（AUD-2 的核心）────────────────────────────────


@pytest.mark.parametrize(
    "foreign",
    ["project_P1", "team_T1", "agent_other", "project_P1_", "agent_", "whatever"],
)
def test_agent_host_rejects_any_foreign_namespace(foreign: str) -> None:
    """`host_kind="agent"` 只能写进**该 agent 自己**的命名空间 ⇒ 越出即 403。"""
    with pytest.raises(OctopError) as excinfo:
        ns.resolve_namespace_to_adopt(
            agent_id=AGENT_ID, target_host="agent", target_namespace=foreign
        )
    assert excinfo.value.code == ErrorCode.FORBIDDEN
    assert excinfo.value.status == 403


@pytest.mark.parametrize("host_spec", ["agent:project_P1", "agent:team_T1", "agent:agent_other"])
def test_agent_host_rejects_namespace_embedded_in_target_host(host_spec: str) -> None:
    """**第二条通道**：`host:namespace` 与表单字段是同一个入口，必须一并约束。"""
    with pytest.raises(OctopError) as excinfo:
        ns.resolve_namespace_to_adopt(
            agent_id=AGENT_ID, target_host=host_spec, target_namespace=None
        )
    assert excinfo.value.code == ErrorCode.FORBIDDEN


def test_field_and_embedded_namespace_are_both_validated() -> None:
    """两个候选**都**过门：即使将来 adopt 的优先级翻转，也仍然安全。"""
    with pytest.raises(OctopError) as excinfo:
        ns.resolve_namespace_to_adopt(
            agent_id=AGENT_ID,
            target_host=f"agent:{ns.allowed_agent_namespace(AGENT_ID)}",
            target_namespace="project_P1",
        )
    assert excinfo.value.code == ErrorCode.FORBIDDEN


def test_agent_host_pins_the_agents_own_namespace_when_unspecified() -> None:
    """**正对照**：不指定 namespace 时钉死为该 agent 自己的（而不是让包内 manifest 决定）。"""
    assert ns.resolve_namespace_to_adopt(
        agent_id=AGENT_ID, target_host="agent", target_namespace=None
    ) == ("agent", ns.allowed_agent_namespace(AGENT_ID))


def test_agent_host_accepts_its_own_namespace_explicitly() -> None:
    """**正对照**：显式写自己的命名空间 ⇒ 放行。"""
    own = ns.allowed_agent_namespace(AGENT_ID)
    assert ns.resolve_namespace_to_adopt(
        agent_id=AGENT_ID, target_host="agent", target_namespace=own
    ) == ("agent", own)


@pytest.mark.parametrize("host_kind", ["openclaw", "hermes", "octopmemory"])
def test_external_hosts_keep_their_namespace_freedom(host_kind: str) -> None:
    """外部宿主写的是 `~/.octopmemory/` / `~/.openclaw/`，**不在** Octop 的隔离命名空间空间里
    ⇒ 不套用「只能写自己 ns」的收紧，否则会打死「迁出到 OpenClaw」这条已发布的 UI 主流程。"""
    assert ns.resolve_namespace_to_adopt(
        agent_id=AGENT_ID, target_host=host_kind, target_namespace="openclaw__x"
    ) == (host_kind, "openclaw__x")


def test_external_host_still_gets_the_format_gate() -> None:
    """外部宿主也必须过格式门 —— 它们的 namespace 同样拼进路径。"""
    with pytest.raises(OctopError) as excinfo:
        ns.resolve_namespace_to_adopt(
            agent_id=AGENT_ID, target_host="openclaw", target_namespace="../../pwned"
        )
    assert excinfo.value.code == ErrorCode.SLASH_BAD_ARGS
    assert excinfo.value.status == 400


@pytest.mark.parametrize("host_kind", ["", "unknown", "claude", "agent2"])
def test_unknown_host_kind_is_rejected(host_kind: str) -> None:
    """宿主名是**闭集**，认不出显式拒绝、不退回默认。"""
    with pytest.raises(OctopError) as excinfo:
        ns.resolve_namespace_to_adopt(
            agent_id=AGENT_ID, target_host=host_kind, target_namespace=None
        )
    assert excinfo.value.code == ErrorCode.SLASH_BAD_ARGS


# ── 包内 manifest 通道（审计未覆盖，实测存在的第二条注入面）──────────────────


@pytest.mark.parametrize(
    "manifest",
    [
        {"agent_name": "../../pwned"},
        {"agent_name": "a/b"},
        {"agent_name": ".."},
        {"agent_name": "x" * 200},
        {"source_namespace": "../evil"},
        {"agent_name": "", "source_namespace": "a\\b"},
    ],
)
def test_manifest_path_fields_are_rejected(manifest: dict[str, Any]) -> None:
    """``adopt()`` 会用包内 `manifest["agent_name"]` 生成目标 namespace
    （`…/adopter.py @252` → `_build_target_namespace @267-268`）⇒ **不需要任何表单字段**
    就能决定写入目录。这条通道必须一并堵上。"""
    with pytest.raises(OctopError) as excinfo:
        ns.assert_manifest_scope_is_safe(manifest)
    assert excinfo.value.code == ErrorCode.SLASH_BAD_ARGS


@pytest.mark.parametrize(
    "manifest",
    [
        {},
        {"agent_name": "a1"},
        {"agent_name": "", "source_namespace": ""},
        {"source_namespace": "agent_a1"},
    ],
)
def test_safe_manifests_pass(manifest: dict[str, Any]) -> None:
    ns.assert_manifest_scope_is_safe(manifest)


# ── 路由：拒绝时 adopt() 一次都不许被调用（写盘之前拦）──────────────────────


class _PkgFile:
    def __init__(self, payload: bytes = b"not-a-real-package") -> None:
        self._payload = payload

    async def read(self) -> bytes:
        return self._payload


def _user(*, is_admin: bool = False, uid: int = 1) -> Any:
    return SimpleNamespace(id=uid, is_admin=is_admin)


def _server(*, owner_id: int = 1, workspace: Any = None) -> Any:
    """最小 server 替身。

    T-57 起 ``adopt`` 也要解析目标文件（``_agent_memory_db_path`` → ``resolve_agent_workspace_dir``
    ＋ ``services.agent_repo``），而 ``pack`` / ``doctor`` 两个既有端点本来就要求这两面 ⇒
    替身补齐它们（默认工作区取临时目录下的固定位置，**不写盘**，本文件的断言与它无关）。
    """
    import tempfile
    from pathlib import Path

    base = (
        Path(workspace)
        if workspace is not None
        else Path(tempfile.gettempdir()) / "octop-t56-test-workspace" / AGENT_ID
    )
    row = SimpleNamespace(agent_id=AGENT_ID, user_id=owner_id, is_shared=0, config_json="{}")
    registry = SimpleNamespace(
        get_row=lambda agent_id: row if agent_id == AGENT_ID else None,
        resolve_workspace_dir=lambda agent_id: base,
    )
    return SimpleNamespace(
        app_runtime=SimpleNamespace(agent_registry=registry),
        services=SimpleNamespace(agent_repo=SimpleNamespace(get=lambda agent_id: row)),
        paths=SimpleNamespace(ensure_agent_workspace=lambda agent_id: base),
    )


class _AdoptSpy:
    """记录 `adopt()` 的调用（含 kwargs）——「拒绝时未写盘」的证据。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, pkg_path: Any, target_host: str, **kwargs: Any) -> Any:
        self.calls.append({"target_host": target_host, **kwargs})
        return SimpleNamespace(to_dict=lambda: {"target_namespace": kwargs.get("target_namespace")})


@pytest.fixture
def adopt_env(monkeypatch: pytest.MonkeyPatch) -> _AdoptSpy:
    """把路由里两个重活替换成替身：postgres 拒绝检查、包内 manifest 读取。"""
    import octop_memory.operations.migration.portable as portable_pkg

    spy = _AdoptSpy()
    monkeypatch.setattr(portable_pkg, "adopt", spy)
    monkeypatch.setattr(mp, "_refuse_postgres_portable", lambda *_a, **_k: None)
    monkeypatch.setattr(mp, "_read_manifest_or_value_error", lambda _path: {"agent_name": AGENT_ID})
    return spy


async def test_route_rejects_foreign_project_namespace(adopt_env: _AdoptSpy) -> None:
    """**AUD-2 主断言**：agent 的属主 adopt 到自己不是成员的项目 ns ⇒ 403，且**没写盘**。"""
    with pytest.raises(OctopError) as excinfo:
        await mp.adopt_agent_memory(
            agent_id=AGENT_ID,
            pkg_file=_PkgFile(),
            target_host="agent",
            target_namespace="project_P1",
            on_conflict="skip",
            host_rewrite="keep",
            dry_run=False,
            user=_user(),
            server=_server(),
            as_user=None,
        )
    assert excinfo.value.code == ErrorCode.FORBIDDEN
    assert excinfo.value.status == 403
    assert adopt_env.calls == [], "拒绝必须发生在写盘之前 —— adopt() 一次都不能被调用"


async def test_route_rejects_foreign_namespace_via_target_host(adopt_env: _AdoptSpy) -> None:
    with pytest.raises(OctopError) as excinfo:
        await mp.adopt_agent_memory(
            agent_id=AGENT_ID,
            pkg_file=_PkgFile(),
            target_host="agent:project_P1",
            target_namespace=None,
            on_conflict="skip",
            host_rewrite="keep",
            dry_run=False,
            user=_user(),
            server=_server(),
            as_user=None,
        )
    assert excinfo.value.code == ErrorCode.FORBIDDEN
    assert adopt_env.calls == []


async def test_route_rejects_traversal_namespace(adopt_env: _AdoptSpy) -> None:
    """路径穿越 ⇒ 400，且没写盘（`mkdir(parents=True)` 在 adopt 内部）。"""
    with pytest.raises(OctopError) as excinfo:
        await mp.adopt_agent_memory(
            agent_id=AGENT_ID,
            pkg_file=_PkgFile(),
            target_host="agent",
            target_namespace="../../pwned",
            on_conflict="skip",
            host_rewrite="keep",
            dry_run=False,
            user=_user(),
            server=_server(),
            as_user=None,
        )
    assert excinfo.value.code == ErrorCode.SLASH_BAD_ARGS
    assert excinfo.value.status == 400
    assert adopt_env.calls == []


async def test_route_accepts_own_namespace_and_pins_it(adopt_env: _AdoptSpy) -> None:
    """**正对照**：写自己 agent 的 ns ⇒ 放行，且喂给 adopt 的正是该 ns（功能没被挡死）。"""
    own = ns.allowed_agent_namespace(AGENT_ID)
    response = await mp.adopt_agent_memory(
        agent_id=AGENT_ID,
        pkg_file=_PkgFile(),
        target_host="agent",
        target_namespace=own,
        on_conflict="skip",
        host_rewrite="keep",
        dry_run=False,
        user=_user(),
        server=_server(),
        as_user=None,
    )
    assert response.status_code == 200
    assert len(adopt_env.calls) == 1
    assert adopt_env.calls[0]["target_namespace"] == own


async def test_route_pins_own_namespace_when_unspecified(adopt_env: _AdoptSpy) -> None:
    """不指定 namespace ⇒ 服务端钉死为自己那个，**不让包内 manifest 决定**。"""
    await mp.adopt_agent_memory(
        agent_id=AGENT_ID,
        pkg_file=_PkgFile(),
        target_host="agent",
        target_namespace=None,
        on_conflict="skip",
        host_rewrite="keep",
        dry_run=False,
        user=_user(),
        server=_server(),
        as_user=None,
    )
    assert adopt_env.calls[0]["target_namespace"] == ns.allowed_agent_namespace(AGENT_ID)


async def test_route_rejects_unsafe_manifest(
    adopt_env: _AdoptSpy, monkeypatch: pytest.MonkeyPatch
) -> None:
    """包内 `agent_name` 穿越 ⇒ 400 且没写盘（第二条通道的路由级证据）。"""
    monkeypatch.setattr(
        mp, "_read_manifest_or_value_error", lambda _path: {"agent_name": "../../pwned"}
    )
    with pytest.raises(OctopError) as excinfo:
        await mp.adopt_agent_memory(
            agent_id=AGENT_ID,
            pkg_file=_PkgFile(),
            target_host="agent",
            target_namespace=None,
            on_conflict="skip",
            host_rewrite="keep",
            dry_run=False,
            user=_user(),
            server=_server(),
            as_user=None,
        )
    assert excinfo.value.code == ErrorCode.SLASH_BAD_ARGS
    assert adopt_env.calls == []


# ── 路由：sources 清单作用域（AUD-1）────────────────────────────────────────


def test_agent_id_of_namespace() -> None:
    assert mp._agent_id_of_namespace("agent_a1") == "a1"
    assert mp._agent_id_of_namespace("agent_a1_") == "a1"
    assert mp._agent_id_of_namespace("project_P1") is None
    assert mp._agent_id_of_namespace("team_T1") is None
    assert mp._agent_id_of_namespace("") is None


_ROWS: list[dict[str, Any]] = [
    {
        "host_kind": "agent",
        "db_path": "/home/u/.octop/agents/a1/memory.sqlite",
        "namespace": "agent_a1",
        "agent_name": "a1",
    },
    {
        "host_kind": "agent",
        "db_path": "/home/u/.octop/agents/a2/memory.sqlite",
        "namespace": "agent_a2",
        "agent_name": "a2",
    },
    {
        "host_kind": "agent",
        "db_path": "/home/u/.octop/agents/a1/memory.sqlite",
        "namespace": "project_P1",
        "agent_name": "a1",
    },
    {
        "host_kind": "openclaw",
        "db_path": "/home/u/.openclaw/octopmemory/x/memory.sqlite",
        "namespace": "openclaw__x",
        "agent_name": "x",
    },
]


def test_non_admin_sees_only_owned_agents_and_no_absolute_paths() -> None:
    """**AUD-1 主断言**：普通用户看不到他人 agent 的条目，响应里**不含绝对路径**。"""
    rows = mp._scoped_source_rows(_ROWS, owned={"a1"}, is_admin=False)
    assert [r["namespace"] for r in rows] == ["agent_a1"]
    assert all("db_path" not in r for r in rows)


def test_non_admin_does_not_see_other_agents_or_external_stores() -> None:
    rows = mp._scoped_source_rows(_ROWS, owned={"a1"}, is_admin=False)
    namespaces = {r["namespace"] for r in rows}
    assert "agent_a2" not in namespaces  # 他人 agent
    assert "openclaw__x" not in namespaces  # 外部宿主 store
    assert "project_P1" not in namespaces  # 项目 store 不走这个端点


def test_admin_keeps_the_host_level_listing_with_paths() -> None:
    """**正对照**：admin 仍是主机级全量，含 `db_path`（与改动前一致）。"""
    rows = mp._scoped_source_rows(_ROWS, owned=set(), is_admin=True)
    assert rows == _ROWS
    assert rows[0]["db_path"]


def test_owner_of_both_agents_sees_both() -> None:
    rows = mp._scoped_source_rows(_ROWS, owned={"a1", "a2"}, is_admin=False)
    assert [r["namespace"] for r in rows] == ["agent_a1", "agent_a2"]


async def test_sources_route_uses_the_caller_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    """路由层：非 admin 走裁剪；admin 走全量。"""
    import octop_memory.operations.migration.portable as portable_pkg

    monkeypatch.setattr(
        portable_pkg,
        "list_sources",
        lambda: [SimpleNamespace(to_dict=lambda row=row: dict(row)) for row in _ROWS],
    )
    repo = SimpleNamespace(
        list_by_user=lambda uid: [SimpleNamespace(agent_id="a1")],
    )
    server = SimpleNamespace(services=SimpleNamespace(agent_repo=repo))

    body = (await mp.list_portable_sources(user=_user(is_admin=False), server=server)).body
    payload = __import__("json").loads(body)
    assert [r["namespace"] for r in payload["sources"]] == ["agent_a1"]
    assert all("db_path" not in r for r in payload["sources"])

    admin = (await mp.list_portable_sources(user=_user(is_admin=True), server=server)).body
    assert len(__import__("json").loads(admin)["sources"]) == len(_ROWS)
