"""批次⑦ C2：``create()`` 三条拒绝路径的**原子性**（真实 booted 服务 + httpx）。

判据（每条拒绝都逐字断言）：``projects`` / ``team_runs`` / ``threads`` / ``team_run_members``
四张表**一行不增**。修复前第一个写是 ``create_project``，其后三条拒绝都会留下孤儿行：

* 同秒 ``run_id`` 冲突 ⇒ 409 ``TEAM_RUN_CONFLICT``（project 已写）；
* manifest 成员缺 ``role`` ⇒ 400 ``TEAM_ROLE_UNKNOWN``（project + run + room thread 已写）；
* manifest 角色重复 ⇒ 400 ``PROJECT_MEMBER_INVALID``（同上）。

★ 接线纪律（与 STANDING-RULES R12 同）：本文件用 ``env`` fixture 的**真实 booted
``OctopServer``**，**不注入** ``workspace_for``、不 monkeypatch 运行服务、不用替身工作区；
花名册只用生产访问器 ``AgentManager.team_workspace_for`` 写进团队工作区并回读。

★ 秒级 ``run_id`` 陷阱：冲突用例靠 ``monkeypatch`` **固定** ``run_id_for`` 构造，不靠「同一秒
连发两次」；其余用例每个测试只发一次会成功的 create。

仅本地可观测：全部经 ``httpx`` 打真实路由，断言对象是本进程的临时 ``OCTOP_HOME``。
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from octop.infra.errors import ErrorCode, OctopError
from tests.support.auth import create_agent

TEAM_MEMBERS = 2
MANIFEST = ".octop/manifest.json"
FIXED_RUN_ID = "2026-01-02-030405"
RUN_ID_FOR = "octop.infra.agents.teams.run_service.run_id_for"

#: 原子性判据覆盖的四张表（SPEC A3 逐字）。
_TABLES = ("projects", "team_runs", "threads", "team_run_members")

#: repair-5：第五张表 —— ``create_project`` 在 KB 可用时会顺手建一个空 KB，
#: 补偿只删 project 的话，四表全 0 也照样每次泄漏 1 个 KB（配额 20）。
_KB_TABLES = (*_TABLES, "knowledge_bases")

_Env = tuple[httpx.AsyncClient, Any, dict[str, str]]


def _table_counts(srv: Any) -> dict[str, int]:
    """四表行数，**直查表**（不经 service 计数）——「拒绝即零写入」的判据。"""
    sql = (
        "SELECT (SELECT COUNT(*) FROM projects), (SELECT COUNT(*) FROM team_runs),"
        " (SELECT COUNT(*) FROM threads), (SELECT COUNT(*) FROM team_run_members)"
    )
    with srv.services.repos.db.connect() as conn:
        row = tuple(conn.execute(sql).fetchone())
    return dict(zip(_TABLES, (int(value) for value in row), strict=True))


def _table_counts_with_kb(srv: Any) -> dict[str, int]:
    """五表行数（四表 + ``knowledge_bases``），**直查表**；四表版本语义不变、两者并存。"""
    sql = (
        "SELECT (SELECT COUNT(*) FROM projects), (SELECT COUNT(*) FROM team_runs),"
        " (SELECT COUNT(*) FROM threads), (SELECT COUNT(*) FROM team_run_members),"
        " (SELECT COUNT(*) FROM knowledge_bases)"
    )
    with srv.services.repos.db.connect() as conn:
        row = tuple(conn.execute(sql).fetchone())
    return dict(zip(_KB_TABLES, (int(value) for value in row), strict=True))


def _enable_kb(monkeypatch: pytest.MonkeyPatch) -> None:
    """打开 KB 门，否则「KB 计数不变」是**恒真**的假绿。

    默认环境 KB 不可用（没配 embedding 模型 ⇒ ``get_capability(...)["usable"]`` 为假，
    ``create_project`` 只记一条 info 就跳过 KB 分支）。两层都打：
    ① ``projects.service.get_capability`` ⇒ ``{"usable": True}``（``bind_kb`` 的唯一判据）；
    ② ``knowledge.service.assert_knowledge_usable`` ⇒ no-op（``create_base`` 自带的同一道门）。

    门是否真打开由 ``test_a_successful_create_binds_a_knowledge_base`` 正向对照：
    成功 create ⇒ ``knowledge_bases`` 必须 +1。
    """
    monkeypatch.setattr(
        "octop.infra.projects.service.get_capability", lambda *args, **kwargs: {"usable": True}
    )
    monkeypatch.setattr(
        "octop.infra.knowledge.service.assert_knowledge_usable", lambda *args, **kwargs: None
    )


async def _stopped_team(
    env: _Env, *, name: str
) -> tuple[httpx.AsyncClient, Any, dict[str, str], str, list[str]]:
    """建团队（团队清单仍是既有 ≥2 规则）→ 停宿主 → 断言活句柄确实取不到。"""
    client, srv, auth = env
    members = [await create_agent(client, auth, name=f"{name}-m{i}") for i in range(TEAM_MEMBERS)]
    created = await client.post(
        "/api/teams", headers=auth, json={"name": name, "member_ids": members}
    )
    assert created.status_code in (200, 201), created.text
    team_id = str(created.json()["agent_id"])

    stopped = await client.post(f"/api/agents/{team_id}/stop", headers=auth)
    assert stopped.status_code == 204, stopped.text
    with pytest.raises(OctopError) as err:
        srv.app_runtime.agent_registry.get_agent(team_id)
    assert err.value.code is ErrorCode.AGENT_NOT_RUNNING, err.value.code
    return client, srv, auth, team_id, members


def _seed_manifest(srv: Any, team_id: str, members: list[dict[str, Any]]) -> None:
    """把花名册写进团队工作区 —— **只经生产访问器**，并回读确认真的落盘。

    这里收原始 dict（而不是 (agent_id, role) 元组），因为「成员**缺** ``role`` 键」正是
    三条判据之一，元组 helper 表达不了缺键。
    """
    workspace = srv.app_runtime.agent_registry.team_workspace_for(team_id)
    assert workspace is not None
    workspace.write_text(MANIFEST, json.dumps({"members": members}), force=True)
    raw = workspace.read_text(MANIFEST)
    assert raw is not None and json.loads(raw)["members"] == members


async def _create(
    client: httpx.AsyncClient, auth: dict[str, str], team_id: str, goal: str
) -> httpx.Response:
    return await client.post(
        "/api/team/runs",
        headers=auth,
        json={"team_agent_id": team_id, "goal": goal, "tier": "quick"},
    )


# ── 三条拒绝：四表一行不增 ───────────────────────────────────────────────────


async def test_a_run_id_conflict_leaves_no_new_rows(
    env: _Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """同秒 ``run_id`` 冲突 ⇒ **409** ``TEAM_RUN_CONFLICT``，且四表逐字不变。

    冲突用**固定 run id** 构造（``monkeypatch`` 打 ``run_service_module.run_id_for``）：
    第一次 create 真的建出 run，第二次撞上同一个 id。修复前 409 抛在 ``create_project``
    **之后**，所以第二次请求会白白留下一个 project 行 —— 本用例就是钉这一条的。
    """
    client, srv, auth, team_id, members = await _stopped_team(env, name="atomic-conflict")
    _seed_manifest(
        srv,
        team_id,
        [
            {"agent_id": team_id, "role": "lead"},
            {"agent_id": members[0], "role": "backend"},
        ],
    )
    monkeypatch.setattr(RUN_ID_FOR, lambda *a, **k: FIXED_RUN_ID)

    first = await _create(client, auth, team_id, "第一次（占住 id）")
    assert first.status_code == 201, first.text
    assert first.json()["run_id"] == FIXED_RUN_ID
    before = _table_counts(srv)

    second = await _create(client, auth, team_id, "第二次（撞 id）")

    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "TEAM_RUN_CONFLICT"
    assert _table_counts(srv) == before, "409 之前不得再写 project / run / thread / member"


async def test_a_member_without_a_role_leaves_no_new_rows(env: _Env) -> None:
    """manifest 成员**缺** ``role`` 键 ⇒ **400** ``TEAM_ROLE_UNKNOWN``，且四表逐字不变。"""
    client, srv, auth, team_id, members = await _stopped_team(env, name="atomic-no-role")
    _seed_manifest(
        srv,
        team_id,
        [{"agent_id": team_id, "role": "lead"}, {"agent_id": members[0]}],  # ← 没有 role 键
    )
    before = _table_counts(srv)

    refused = await _create(client, auth, team_id, "缺 role 必须在第一个写之前被拒")

    assert refused.status_code == 400, refused.text
    assert refused.json()["error"]["code"] == "TEAM_ROLE_UNKNOWN"
    assert _table_counts(srv) == before, "400 之前不得写 project / run / thread / member"


async def test_a_duplicate_roster_role_leaves_no_new_rows(env: _Env) -> None:
    """manifest 角色重复 ⇒ **400** ``PROJECT_MEMBER_INVALID``，且四表逐字不变。"""
    client, srv, auth, team_id, members = await _stopped_team(env, name="atomic-dup-role")
    _seed_manifest(
        srv,
        team_id,
        [
            {"agent_id": team_id, "role": "backend"},
            {"agent_id": members[0], "role": "backend"},
        ],
    )
    before = _table_counts(srv)

    refused = await _create(client, auth, team_id, "重复角色必须在第一个写之前被拒")

    assert refused.status_code == 400, refused.text
    assert refused.json()["error"]["code"] == "PROJECT_MEMBER_INVALID"
    assert _table_counts(srv) == before, "400 之前不得写 project / run / thread / member"


# ── 反向对照：合法花名册照常建出 run ────────────────────────────────────────


async def test_a_valid_manifest_still_creates_the_run_with_every_member(env: _Env) -> None:
    """反向对照：合法 manifest（lead + backend + qa）⇒ **201**，成员行齐全。"""
    client, srv, auth, team_id, members = await _stopped_team(env, name="atomic-ok")
    _seed_manifest(
        srv,
        team_id,
        [
            {"agent_id": team_id, "role": "lead"},
            {"agent_id": members[0], "role": "backend"},
            {"agent_id": members[1], "role": "qa"},
        ],
    )
    before = _table_counts(srv)

    created = await _create(client, auth, team_id, "合法花名册照常建 run")

    assert created.status_code == 201, created.text
    run_id = str(created.json()["run_id"])
    roles = {row.role for row in srv.services.team_run_repo.list_members(run_id)}
    assert roles == {"lead", "backend", "qa"}, roles
    after = _table_counts(srv)
    assert after["projects"] == before["projects"] + 1
    assert after["team_runs"] == before["team_runs"] + 1
    assert after["team_run_members"] == before["team_run_members"] + 3


async def test_a_lead_only_manifest_still_creates_the_run(env: _Env) -> None:
    """反向对照（A4 · 不得误伤）：lead-only ⇒ **201** 且只落 1 行成员。"""
    client, srv, auth, team_id, _members = await _stopped_team(env, name="atomic-lead-only")
    _seed_manifest(srv, team_id, [{"agent_id": team_id, "role": "lead"}])

    created = await _create(client, auth, team_id, "lead-only 必须放行")

    assert created.status_code == 201, created.text
    run_id = str(created.json()["run_id"])
    rows = srv.services.team_run_repo.list_members(run_id)
    assert len(rows) == 1  # lead 是合法 roster 角色 —— 不得写成 `>= 2`
    assert rows[0].role == "lead"


# ── 第一个写**之后**失败的三条路径（批次⑧ D2）：补偿删除 + 并发映射为 409 ──────
# 与上面「写前拒绝」的区别：这些失败发生时 project / run / thread 已经落库，所以判据里
# 多了一层「**只**清本次创建的」。构造全部确定性（monkeypatch 抛错 / 遮住写前判定），
# 不用 sleep、不用真并发 —— 三遍必须同结果。


def _normal_manifest(team_id: str, members: list[str]) -> list[dict[str, Any]]:
    """lead + 若干普通角色的合法花名册（成员写失败用例需要 ≥2 人）。"""
    return [
        {"agent_id": team_id, "role": "lead"},
        {"agent_id": members[0], "role": "backend"},
    ]


async def test_a_failed_room_thread_leaves_no_new_rows(
    env: _Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """① 房间线程创建失败 ⇒ project + run 必须被补偿删除（四表逐字不变）。

    生产接线里 ``_open_room`` 走 boot 绑定的 gateway；把它换成确定性抛错即可复现
    「project + run 已写，房间线程没开成」这一刻，不依赖任何时序。

    ★ 异常会**穿过 httpx**：Starlette 对未注册的 500 类异常在渲染完 500 之后仍会
    re-raise（``raise_app_exceptions``），所以这里用 ``pytest.raises`` 接住 —— 判据仍是
    后面的四表断言，不是响应码。
    """
    client, srv, auth, team_id, members = await _stopped_team(env, name="atomic-room-fail")
    _seed_manifest(srv, team_id, _normal_manifest(team_id, members))
    _enable_kb(monkeypatch)
    registry = srv.services.team_run_service()._gateway.thread_registry  # noqa: SLF001
    before = _table_counts(srv)
    before_kb = _table_counts_with_kb(srv)

    def _room_fails(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("room thread creation failed")

    monkeypatch.setattr(registry, "create_thread", _room_fails)

    with pytest.raises(RuntimeError, match="room thread creation failed"):
        await _create(client, auth, team_id, "房间线程失败")

    assert _table_counts(srv) == before, "房间线程失败后不得留 project / run"
    assert _table_counts_with_kb(srv) == before_kb, "失败 create 不得泄漏空 KB（五表判据）"


async def test_a_lost_run_id_race_leaves_no_new_rows_and_keeps_the_winner(
    env: _Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """② 竞态窗口撞 ``team_runs.run_id`` UNIQUE ⇒ **409** ``TEAM_RUN_CONFLICT`` + 零新增。

    确定性构造（否掉「真并发」的 flaky）：固定 ``run_id_for`` ⇒ 赢家先建出来；再把
    ``team_run_repo.get`` 遮成 ``None``，模拟「输家的写前判定看不见赢家」的窗口 ⇒ 输家
    在 INSERT 上撞 UNIQUE。修复要求：映射为 409（不是裸 500），且 **stage-aware** ——
    只删输家建的 project，赢家的 run / members 原样活着。

    ★ 断言顺序是刻意的：**先断四表**再断「没有裸异常 / 是 409」。修复前这里红在四表
    （孤儿 project），若只修了映射没修补偿，则红在第二条 —— 两种缺陷各自有专属红点。
    """
    client, srv, auth, team_id, members = await _stopped_team(env, name="atomic-race")
    _seed_manifest(srv, team_id, _normal_manifest(team_id, members))
    _enable_kb(monkeypatch)
    monkeypatch.setattr(RUN_ID_FOR, lambda *a, **k: FIXED_RUN_ID)

    winner = await _create(client, auth, team_id, "赢家")
    assert winner.status_code == 201, winner.text
    winner_id = str(winner.json()["run_id"])
    winner_members = len(srv.services.team_run_repo.list_members(winner_id))
    assert winner_members == 2
    before = _table_counts(srv)
    before_kb = _table_counts_with_kb(srv)
    monkeypatch.setattr(srv.services.team_run_repo, "get", lambda run_id: None)

    loser: httpx.Response | None = None
    raised: BaseException | None = None
    try:
        loser = await _create(client, auth, team_id, "输家（撞 UNIQUE）")
    except Exception as exc:  # 修复前是裸 IntegrityError（Starlette re-raise）
        raised = exc

    assert _table_counts(srv) == before, "撞 UNIQUE 的输家不得留下任何行（孤儿 project）"
    assert _table_counts_with_kb(srv) == before_kb, "输家绑的空 KB 也必须被撤销"
    assert raised is None, f"并发撞 UNIQUE 必须映射成 409，而不是 {raised!r}"
    assert loser is not None and loser.status_code == 409, loser and loser.text
    assert loser.json()["error"]["code"] == "TEAM_RUN_CONFLICT"
    # stage-aware：赢家的 run 与 members 必须一条不少。
    assert len(srv.services.team_run_repo.list_members(winner_id)) == winner_members


async def test_a_failing_member_write_leaves_no_partial_rows(
    env: _Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """③ 非 UNIQUE 的成员写失败（第 2 次 ``add_member`` 抛错）⇒ 半成品被全清。

    第 1 次调用真的写进一行 member ⇒ 半成品确实存在过；失败后 project / run / thread /
    已写 members（以及 project 绑的空 KB）必须一并清掉（四表 + KB 逐字不变）。
    异常同样穿过 httpx（见 ①）。
    """
    client, srv, auth, team_id, members = await _stopped_team(env, name="atomic-member-fail")
    _seed_manifest(srv, team_id, _normal_manifest(team_id, members))
    _enable_kb(monkeypatch)
    written = srv.services.team_run_repo.add_member
    calls = {"n": 0}

    def _second_member_fails(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] >= 2:
            raise RuntimeError("member write failed (non-UNIQUE)")
        return written(*args, **kwargs)

    before = _table_counts(srv)
    before_kb = _table_counts_with_kb(srv)
    monkeypatch.setattr(srv.services.team_run_repo, "add_member", _second_member_fails)

    with pytest.raises(RuntimeError, match="member write failed"):
        await _create(client, auth, team_id, "第 2 个成员写失败")

    assert calls["n"] == 2, "必须先真的写进 1 行成员，半成品才成立"
    assert _table_counts(srv) == before, "成员写失败后不得留 project / run / thread / member"
    assert _table_counts_with_kb(srv) == before_kb, "失败 create 不得泄漏空 KB（五表判据）"


# ── repair-5 正向对照：KB 门真的打开时，成功 create 才会建出 KB ────────────────


async def test_a_successful_create_binds_a_knowledge_base(
    env: _Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """正向对照（非恒真自证）：KB 可用时，**成功**的 create ⇒ ``knowledge_bases`` +1。

    没有它，上面三条的「KB 计数不变」可能只是「KB 压根没建过」—— 恒真假绿。
    它也顺带证明 ``_enable_kb`` 打的二层门在真实 booted 服务里确实生效。
    """
    client, srv, auth, team_id, members = await _stopped_team(env, name="atomic-kb-control")
    _seed_manifest(srv, team_id, _normal_manifest(team_id, members))
    _enable_kb(monkeypatch)
    before = _table_counts_with_kb(srv)

    created = await _create(client, auth, team_id, "成功建 run（绑定 KB）")

    assert created.status_code == 201, created.text
    after = _table_counts_with_kb(srv)
    assert after["knowledge_bases"] == before["knowledge_bases"] + 1, (
        "KB 门没真的打开 —— 失败用例的 KB 断言会是恒真假绿"
    )
    assert after["projects"] == before["projects"] + 1
    assert after["team_runs"] == before["team_runs"] + 1
