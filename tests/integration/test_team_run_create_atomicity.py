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
