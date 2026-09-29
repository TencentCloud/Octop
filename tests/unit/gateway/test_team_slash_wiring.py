"""T-49 —— ``/team`` 的 5 处接线：**接线存在**的证明（与"函数正确"分开）。

本文件只回答一个问题：**这两样东西真的从 `server.py` 一路走到了 `SlashCtx` 上吗？**
（"谓词/服务本身对不对"是 T-48 与 `tests/unit/agents/test_slash_team.py` 的事，这里不重复。）

覆盖卡的验收：
* ① owner 经 ``/team <goal>`` 走到 ``service.create``（用**真实** `TeamRunService` + 真 DB）；
* ② **正对照**：非 owner 被拒，且拒绝**来自谓词**（`FORBIDDEN`）—— 必须与
  「authorizer 为 `None` ⇒ 一律拒」**可区分**（后者是 `TEAM_COMMAND_UNKNOWN` +
  `reason="authorizer_unwired"`）。**这条是"半接线"假象的唯一解药。**
* ③ `bind_runtime` 有生产调用者；且**房间线程（dispatch 的前置）只在绑定后才可用**；
* ④ `infra/` 不 import `api/`（AST 查真实 import 语句）。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from octop.config import OctopConfig
from octop.infra.agents.teams.run_service import TeamRunService
from octop.infra.agents.teams.service import TeamService
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.gateway import Gateway
from octop.infra.gateway.slash.ctx import SlashCtx
from octop.infra.gateway.slash.handlers.team import cmd_team
from octop.infra.server import OctopServer
from octop.infra.users.permissions import BASELINE_PERMISSIONS
from octop.infra.utils.paths import PathLayout

TEAM_ID = "ag-team"
MANIFEST = ".octop/manifest.json"


class _Workspace:
    """`BackendWorkspace` 替身：workspace 相对路径 → 文本。"""

    def __init__(self, files: dict[str, str] | None = None) -> None:
        self.files: dict[str, str] = dict(files or {})

    def read_text(self, path: str, *, limit: int = 10_000_000) -> str | None:
        return self.files.get(str(path))

    def write_text(self, path: str, content: str, *, force: bool = False) -> None:
        self.files[str(path)] = content

    def exists(self, path: str) -> bool:
        return str(path) in self.files

    def list_dir(self, path: str = ".") -> list[Any]:
        """**Harness shape** — ``{"path": <workspace-relative>, "is_dir"}`` (T-79)."""
        prefix = "" if str(path) in {"", "."} else str(path).rstrip("/") + "/"
        out: list[Any] = []
        for name in sorted(self.files):
            if not name.startswith(prefix):
                continue
            rest = name[len(prefix) :]
            if "/" not in rest:
                out.append({"path": name, "is_dir": False})
        return out


class _ThreadRegistry:
    """只够房间线程用：记录调用并返回固定 id。"""

    CHANNEL_DASHBOARD = "dashboard"

    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    @staticmethod
    def make_key(**kwargs: Any) -> str:
        return ":".join(str(v) for v in kwargs.values())

    def create_thread(self, **kwargs: Any) -> str:
        self.created.append(kwargs)
        return "thread-room-1"


class _StubGateway:
    def __init__(self) -> None:
        self.thread_registry = _ThreadRegistry()


def _members() -> str:
    return json.dumps(
        {
            "members": [
                {"agent_id": TEAM_ID, "role": "lead"},
                {"agent_id": "ag-be", "role": "backend"},
                {"agent_id": "ag-qa", "role": "qa"},
            ]
        }
    )


@pytest.fixture
def real_service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """**真实** `TeamRunService`：真 DB、真迁移、真 roster/manifest 读取。"""
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    owner = services.user_repo.create(
        username="owner",
        password_hash="h",
        role="user",
        # A real user row gets the baseline grants (``UserManager.create``); a raw
        # repo row gets ``[]``, which the projects feature gate then refuses.
        permissions=sorted(BASELINE_PERMISSIONS),
    )
    other = services.user_repo.create(
        username="other",
        password_hash="h",
        role="user",
        permissions=sorted(BASELINE_PERMISSIONS),
    )
    services.agent_repo.create(agent_id=TEAM_ID, user_id=owner, name="Team", kind="team")
    workspace = _Workspace({MANIFEST: _members()})
    accessor = lambda agent_id: workspace if agent_id == TEAM_ID else None  # noqa: E731
    service = TeamRunService(
        services=services,
        team_service=TeamService(services.repos, workspace_for=accessor),
        workspace_for=accessor,
    )
    return SimpleNamespace(
        services=services,
        service=service,
        owner_id=int(owner),
        other_id=int(other),
        tmp=tmp_path,
    )


def _agent_manager(row: Any, tmp_path: Path) -> Any:
    return SimpleNamespace(
        paths=PathLayout(tmp_path / "ws"),
        octop_config=OctopConfig(),
        get_row=lambda _aid: row,
    )


def _ctx_from(
    *,
    service: Any,
    authorizer: Any,
    user_id: int,
    agent_manager: Any,
    services: Any = None,
) -> SlashCtx:
    """**走生产的 `GlobalProcessor._slash_ctx`**，而不是手搓 `SlashCtx`。

    手搓 ctx 只能证明 handler 会用给定字段；这里要证明的恰恰是**字段真的被塞进去了**，
    所以必须经过 `GlobalProcessor`（第 2、3 处接线）。`user_repo` 用真的，因为
    ``build_slash_ctx`` 会 ``user_repo.get(user_id)`` 取 locale。
    """
    from octop.infra.gateway.process.processor import GlobalProcessor

    def _repo(name: str) -> Any:
        return getattr(services, name, None) or MagicMock()

    processor = GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=_repo("session_repo"),
        audit_repo=_repo("audit_repo"),
        agent_repo=_repo("agent_repo"),
        user_repo=_repo("user_repo"),
        connector_repo=_repo("connector_repo"),
        dispatcher=MagicMock(),
        team_run_service=service,
        authorize_agent_action=authorizer,
    )
    return processor._slash_ctx(  # noqa: SLF001 - 要测的就是这处接线
        agent_id=TEAM_ID, user_id=user_id, channel_type="dashboard", session_key="sk"
    )


class _Sink:
    def __init__(self) -> None:
        self.lines: list[str] = []

    async def text(self, value: str) -> None:
        self.lines.append(value)


async def _team(goal: str, ctx: SlashCtx) -> str:
    """`/team <goal>` —— 无子命令词时整串就是 goal（`handlers/team.py @238-241`）。"""
    sink = _Sink()
    await cmd_team(MagicMock(), SimpleNamespace(args=goal), ctx, sink)  # type: ignore[arg-type]
    return "\n".join(sink.lines)


def _adapter(user_ids: Any) -> Any:
    """**生产的适配器**：`OctopServer._authorize_agent_action`（未绑定实例直接调）。

    只把 `user_manager` 换成查得出人的替身（`UserManager` 挂在 server 上、不在
    `SharedServices` 里，且要先把用户装进内存表）；**被测的代码是生产适配器本身** ——
    "把 `user_id` 解析成 `User` 再交给 T-48 的谓词"。
    """

    def _get(uid: int) -> Any:
        if uid not in user_ids:
            return None
        return SimpleNamespace(id=uid, is_admin=False, permissions=["projects"])

    server_like = SimpleNamespace(user_manager=SimpleNamespace(get_by_id=_get))
    return lambda row, uid: OctopServer._authorize_agent_action(  # noqa: SLF001
        server_like, row, uid
    )


# ── 接线 1→2→3：server 注入的 handle 真的到达 SlashCtx ────────────────────────


async def test_gateway_keeps_both_handles_and_boot_hands_them_to_the_processor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """第 1、2 处：`Gateway` 收下两个 kwarg，`boot()` 传给 `GlobalProcessor`。

    真跑 `boot()`（把 `ChannelManager` 换成替身，免得起真通道）—— 比读源码断言强：
    它证明的是**运行时**真的送到了。
    """
    from octop.infra.gateway import gateway as gateway_mod

    class _CM:
        def __init__(self, **_kw: Any) -> None: ...
        def set_pre_lock_handler(self, _h: Any) -> None: ...
        async def start(self) -> None: ...
        async def add_channel(self, _c: Any) -> None: ...

    monkeypatch.setattr(gateway_mod, "ChannelManager", _CM)
    monkeypatch.setattr(gateway_mod, "WebSocketChannel", lambda *a, **k: SimpleNamespace())
    monkeypatch.setattr(gateway_mod, "CliChannel", lambda *a, **k: SimpleNamespace())

    repos = MagicMock()
    sentinel_service = object()
    sentinel_auth = object()
    gw = Gateway(
        agent_manager=SimpleNamespace(),
        repos=repos,
        team_run_service=sentinel_service,
        authorize_agent_action=sentinel_auth,  # type: ignore[arg-type]
    )
    await gw.boot()

    assert gw._processor is not None
    assert gw._processor._team_run_service is sentinel_service
    assert gw._processor._authorize_agent_action is sentinel_auth


def test_processor_delivers_both_handles_into_the_slash_ctx(real_service: Any) -> None:
    """第 3 处：`_slash_ctx` 把两个东西传进 `build_slash_ctx`。

    **反证**：同一构造下传 `None` ⇒ ctx 上就是 `None`（说明这条断言不是恒真）。
    """
    row = SimpleNamespace(user_id=real_service.owner_id, kind="team")
    wired = _ctx_from(
        service=real_service.service,
        authorizer=_adapter({real_service.owner_id, real_service.other_id}),
        user_id=real_service.owner_id,
        agent_manager=_agent_manager(row, real_service.tmp),
        services=real_service.services,
    )
    assert wired.team_run_service is real_service.service
    assert wired.authorize_agent_action is not None

    unwired = _ctx_from(
        service=None,
        authorizer=None,
        user_id=real_service.owner_id,
        agent_manager=_agent_manager(row, real_service.tmp),
        services=real_service.services,
    )
    assert unwired.team_run_service is None and unwired.authorize_agent_action is None


# ── ① 端到端：owner 真的建出 run ─────────────────────────────────────────────


async def test_owner_creates_a_run_through_the_slash_command(real_service: Any) -> None:
    """① owner 经 `/team <goal>` 走到 `service.create`，DB 里**真的**多了一行 run。

    这条用例曾是 `xfail(strict=True)`：当时所有者**已经越过**归属谓词（接线是通的），
    失败发生在 `create()` 内部 —— `handlers/team.py` 的 `_create` 传了裸 `user_id`，
    而 `create()` 要 `ProjectActor`（`task-94` 已修，标记随之删除）。

    ⇒ **"接线存在"与"端到端可用"是两件事**：本条同时钉住后者，前者由本文件的另外两条
    （`Gateway.boot` 转发、`_slash_ctx` 落到 `SlashCtx`）覆盖。
    """
    services = real_service.services
    row = SimpleNamespace(user_id=real_service.owner_id, kind="team")
    ctx = _ctx_from(
        service=real_service.service,
        authorizer=_adapter({real_service.owner_id, real_service.other_id}),
        user_id=real_service.owner_id,
        agent_manager=_agent_manager(row, real_service.tmp),
        services=services,
    )

    reply = await _team("把看板做完", ctx)
    assert reply, "应返回一条 run 创建回执"

    projects = services.project_repo.list_for_user(real_service.owner_id)
    assert len(projects) == 1, "创建 run 应同时建出项目行"
    runs = services.team_run_repo.list(team_agent_id=TEAM_ID)
    assert len(runs) == 1, "owner 经 /team 应当真的建出一行 run"
    assert runs[0].project_id == projects[0].id
    assert runs[0].team_agent_id == TEAM_ID
    assert runs[0].goal == "把看板做完"


# ── ② 正对照：非 owner 被"谓词"拒，且与"未注入"可区分 ────────────────────────


async def test_non_owner_is_refused_by_the_predicate(real_service: Any) -> None:
    """② 非 owner ⇒ **`FORBIDDEN`**（来自谓词），且**没有**建出任何东西。"""
    services = real_service.services
    row = SimpleNamespace(user_id=real_service.owner_id, kind="team")  # 属于 owner
    ctx = _ctx_from(
        service=real_service.service,
        authorizer=_adapter({real_service.owner_id, real_service.other_id}),
        user_id=real_service.other_id,  # 但动作由另一个人发出
        agent_manager=_agent_manager(row, real_service.tmp),
        services=services,
    )

    with pytest.raises(OctopError) as ei:
        await _team("把看板做完", ctx)

    assert ei.value.code is ErrorCode.FORBIDDEN, "拒绝必须来自归属谓词"
    assert services.project_repo.list_for_user(real_service.other_id) == []
    assert services.project_repo.list_for_user(real_service.owner_id) == []


async def test_unwired_authorizer_differs_from_a_denied_owner(real_service: Any) -> None:
    """② 的**可区分性**：`authorizer=None` ⇒ `TEAM_COMMAND_UNKNOWN` +
    `reason="authorizer_unwired"`；非 owner ⇒ `FORBIDDEN`。

    若两者不可区分，"接线断了但看着接上了"就会**通过**验收 —— 这条是那枚假象的解药。
    """
    services = real_service.services
    ctx = _ctx_from(
        service=real_service.service,
        authorizer=None,
        user_id=real_service.owner_id,
        agent_manager=_agent_manager(
            SimpleNamespace(user_id=real_service.owner_id, kind="team"), real_service.tmp
        ),
        services=services,
    )
    with pytest.raises(OctopError) as ei:
        await _team("把看板做完", ctx)

    assert ei.value.code is ErrorCode.TEAM_COMMAND_UNKNOWN
    assert ei.value.details["reason"] == "authorizer_unwired"
    assert ei.value.code is not ErrorCode.FORBIDDEN


# ── ③ bind_runtime：生产调用者 + dispatch 前置只在绑定后可用 ────────────────


def test_bind_runtime_has_a_production_caller() -> None:
    """③ `bind_runtime` 在本改动前**全仓 0 个生产调用者**（只有测试）⇒ 现在 server.py 调它。"""
    import octop.infra.server as server_mod

    src = Path(server_mod.__file__).read_text(encoding="utf-8")
    calls = [ln for ln in src.splitlines() if ".bind_runtime(" in ln]
    assert calls, "server.py 必须调用 bind_runtime —— 否则它仍是孤儿"
    assert not any(ln.lstrip().startswith("#") for ln in calls), "不能是注释掉的调用"


def test_room_thread_requires_the_bound_gateway(
    real_service: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """③ dispatch 的前置（房间线程）**只在绑定后才可用**。

    未绑定 ⇒ `_open_room` 返回 `None`（run 没有 room thread）；绑定后 ⇒ 建出 thread。
    这条把"绑定生效"从"函数存在"里分出来。

    ``run_id_for`` 精确到秒，同一个测试里连建两个 run 会撞 id ⇒ 这里让它唯一。
    """
    import octop.infra.agents.teams.run_service as rs

    counter = iter(["run-a", "run-b"])
    monkeypatch.setattr(rs, "run_id_for", lambda: next(counter))
    user = SimpleNamespace(id=real_service.owner_id, is_admin=False, permissions=["projects"])

    run_unbound = real_service.service.create(team_agent_id=TEAM_ID, user=user, goal="未绑定")
    assert run_unbound.room_thread_id is None, "未绑定网关时不该有房间线程"

    real_service.service.bind_runtime(gateway=_StubGateway())
    run_bound = real_service.service.create(team_agent_id=TEAM_ID, user=user, goal="已绑定")
    assert run_bound.room_thread_id == "thread-room-1", "绑定后房间线程必须真的建出来"


# ── ④ §5：infra 不 import api ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "module",
    ["octop.infra.server", "octop.infra.gateway.gateway", "octop.infra.gateway.process.processor"],
)
def test_wiring_modules_do_not_import_the_api_layer(module: str) -> None:
    """④ AST 查真实 import 语句（不去源码找 `api` 这个词：注释里就会出现）。"""
    import importlib

    mod = importlib.import_module(module)
    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append(node.module)
    assert found, "AST 没解析出 import —— 检查本身失效了"
    offenders = [m for m in found if m.startswith("octop.api")]
    assert offenders == [], f"{module} 不得依赖 api 层：{offenders}"
