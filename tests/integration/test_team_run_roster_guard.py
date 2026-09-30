"""E2E-1 / E2E-2（SPEC §回归防护 · ★ 硬门禁）：花名册守卫在**生产接线**上的自证。

★ STANDING-RULES R12 —— E2E-1 必须证明 **boot 接线**，所以本文件：

* 用 ``tests/integration/conftest.py`` 的 ``env`` fixture（真实 booted ``OctopServer`` +
  ``httpx``）：**没有** ``bind_runtime(workspace_for=…)``、没有 monkeypatch 运行服务、
  没有替身工作区（``tests/integration/test_team_runs_api.py`` 的 ``run_env`` 是**注入座**，
  本文件刻意不那样写）；
* 花名册只用**生产访问器** ``AgentManager.team_workspace_for``（``server.py`` 在 boot 时
  交给 run service 的同一个）写进团队工作区，并回读确认落盘；
* 宿主 agent 在 create 之前就被 ``POST /api/agents/{id}/stop`` 停掉，并断言活句柄确实
  取不到（``AGENT_NOT_RUNNING``）—— 旧访问器（``harness_workspace_for_agent``，只认活句柄）
  在这里只会解析出空。

**判别性**（摘掉什么 ⇒ 哪条必然变红）：

* 摘掉空守卫 ⇒ ``test_create_refuses_an_empty_manifest_and_writes_nothing`` 必红：拿不到
  422 ``TEAM_RUN_ROSTER_EMPTY``，而且四表计数会动（会建出零成员 run）。
* 摘掉 boot 接线（``team_run_service(workspace_for=registry.team_workspace_for)``）⇒
  ``test_a_stopped_host_creates_a_plannable_run`` 必红：宿主已停止，活句柄-only 的解析器
  取不到工作区 ⇒ 守卫以 422 ``manifest-unavailable`` 拒绝，201 与 ``:plan`` 两步都到不了。
* 判据从 ``len(trim.kept) == 0`` 改成 ``< TEAM_MIN_MEMBERS(2)`` ⇒
  ``test_a_lead_only_roster_still_creates_the_run`` 必红（lead-only 被误伤）。

仅本地可观测：全部经 ``httpx`` 打真实路由；断言对象是本进程的临时 ``OCTOP_HOME``
（``tmp_octop_home``）—— 不触网、不碰用户目录、不启第二个服务。
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
RUN_SCOPE = "src/octop/infra/agents/teams/run_service.py"

#: A3 判据覆盖的四张表（SPEC A3 逐字：projects / team_runs / threads / team_run_members）。
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
    """建团队（团队清单仍是既有 ≥2 规则）→ **停宿主** → 断言活句柄确实取不到。"""
    client, srv, auth = env
    members = [await create_agent(client, auth, name=f"{name}-m{i}") for i in range(TEAM_MEMBERS)]
    created = await client.post(
        "/api/teams", headers=auth, json={"name": name, "member_ids": members}
    )
    assert created.status_code in (200, 201), created.text
    team_id = str(created.json()["agent_id"])

    stopped = await client.post(f"/api/agents/{team_id}/stop", headers=auth)
    assert stopped.status_code == 204, stopped.text
    registry = srv.app_runtime.agent_registry
    with pytest.raises(OctopError) as err:
        registry.get_agent(team_id)
    assert err.value.code is ErrorCode.AGENT_NOT_RUNNING, err.value.code  # A1 的前提
    return client, srv, auth, team_id, members


def _seed_manifest(
    srv: Any, team_id: str, members: list[dict[str, Any]], *, lead: str | None = None
) -> None:
    """把花名册写进团队工作区 —— **只经生产访问器**，并回读确认真的落盘。"""
    workspace = srv.app_runtime.agent_registry.team_workspace_for(team_id)
    assert workspace is not None
    payload: dict[str, Any] = {"members": members}
    if lead is not None:
        payload["lead_agent_id"] = lead
    workspace.write_text(MANIFEST, json.dumps(payload), force=True)
    raw = workspace.read_text(MANIFEST)
    assert raw is not None and json.loads(raw)["members"] == members


def _draft(owner: str, roles: list[str]) -> dict[str, Any]:
    """一份**合法**的计划草稿：owner 必须落在 run 的成员角色里（``DRAFT_CODES`` B1）。"""
    return {
        "roles": roles,
        "tasks": [
            {
                "id": "e2e-1",
                "title": "E2E-1 计划门",
                "owner": owner,
                "inScope": [RUN_SCOPE],
                "verify": ["uv run pytest -q"],
            }
        ],
    }


async def test_a_stopped_host_creates_a_plannable_run(env: _Env) -> None:
    """E2E-1：宿主**停止** → create **201** → 该 run 有成员行 → ``:plan`` **不再 422**。

    三段按顺序都断言：① 201；② ``team_run_members`` 里该 ``run_id`` ≥1 行（查库）；
    ③ ``:plan``（owner 取保留的**普通**角色 ``backend``）非 422。①② 考的是守卫与接线，
    ②③ 考的正是本批要消灭的缺陷链「零成员行 ⇒ ``:plan`` 422 ``owner-not-in-roles``」。
    """
    client, srv, auth, team_id, members = await _stopped_team(env, name="e2e-1")
    _seed_manifest(
        srv,
        team_id,
        [{"agent_id": team_id, "role": "lead"}, {"agent_id": members[0], "role": "backend"}],
        lead=team_id,
    )
    # R12 自证（FIND-4 改法）：本用例**一次也没注入过**访问器 —— 「boot 是否真的把
    # `workspace_for` 接给了 run service」不再靠私有属性（`service._workspace_for`）断言，
    # 而由下面的**行为**判据证明：create **201** + `team_run_members` ≥1 行 + `:plan` 非 422。
    # 它仍有判别性（实测）：摘掉 boot 接线后宿主已停止，活句柄-only 的解析器取不到工作区 ⇒
    # 守卫以 422 `TEAM_RUN_ROSTER_EMPTY`（`reason=manifest-unavailable`）拒绝，201 与
    # `:plan` 一步都到不了 ⇒ 本用例必红（判别性证据见本文件模块 docstring 与 TEST.md 附录 E）。

    created = await client.post(
        "/api/team/runs",
        headers=auth,
        json={
            "team_agent_id": team_id,
            "goal": "E2E-1 停止的宿主也要建得出可规划 run",
            "tier": "quick",
        },
    )
    assert created.status_code == 201, created.text
    run_id = str(created.json()["run_id"])
    assert created.json()["room_thread_id"], "boot 绑定的 gateway 必须开得出房间线程"

    member_rows = srv.services.team_run_repo.list_members(run_id)
    assert len(member_rows) >= 1, "A1：该 run 的 team_run_members 必须 ≥1 行"
    assert {row.role for row in member_rows} == {"lead", "backend"}
    assert _table_counts(srv)["team_run_members"] >= 1

    planned = await client.post(
        f"/api/team/runs/{run_id}:plan",
        headers=auth,
        json={"draft": _draft("backend", ["lead", "backend"])},
    )
    assert "owner-not-in-roles" not in planned.text, planned.text  # 缺陷原文
    assert planned.status_code != 422, planned.text
    assert planned.status_code == 200, planned.text
    assert planned.json()["draft"]["planStatus"] == "staged"


async def test_create_refuses_an_empty_manifest_and_writes_nothing(env: _Env) -> None:
    """E2E-2：花名册为空（工作区可达、manifest 无成员）⇒ create **422**，四表零新增。

    ``details.reason == "manifest-empty"``：工作区句柄到手了，是清单真的没有成员 —— 与
    「解析链断」的 ``manifest-unavailable`` 是可区分的两种成因（DECISIONS D7）。

    A3 的「四表零新增」在这里有判别力：守卫落在 ``create_project``（第一个写）之前，所以
    一次拒绝不该留下孤儿 project / run / thread / member 行。
    """
    client, srv, auth, team_id, _members = await _stopped_team(env, name="e2e-2")
    _seed_manifest(srv, team_id, [])
    before = _table_counts(srv)

    refused = await client.post(
        "/api/team/runs",
        headers=auth,
        json={"team_agent_id": team_id, "goal": "空花名册必须在 create 就被拒", "tier": "quick"},
    )

    assert refused.status_code == 422, refused.text
    error = refused.json()["error"]
    assert error["code"] == "TEAM_RUN_ROSTER_EMPTY"
    assert error["details"]["reason"] == "manifest-empty"
    assert _table_counts(srv) == before, "A3：拒绝之后四表计数必须逐字不变"


async def test_a_lead_only_roster_still_creates_the_run(env: _Env) -> None:
    """反向对照（A4 · 不得误伤）：花名册只有 ``lead`` ⇒ create **201** 且只落 1 行成员。

    团队清单仍由既有规则把关（``POST /api/teams`` 要 ≥2 成员），但 **run 花名册**的下界就是
    0 之外的一切：``lead`` 是合法 roster 角色。判据若被写成 ``< TEAM_MIN_MEMBERS(2)``，
    这条用例会以 422 变红 —— 这正是它存在的理由（DECISIONS D3/D4）。

    这里**不**再追 ``:plan``：lead-only 花名册里没有可用的 owner 角色
    （``normalize_owner_role("lead") == ""``，lead 管的是 artifact 归属，不是花名册），
    A4 的契约也只是「create 必须放行」。可规划的 run 由 E2E-1 用 ``backend`` 作 owner 覆盖。
    """
    client, srv, auth, team_id, _members = await _stopped_team(env, name="e2e-lead-only")
    _seed_manifest(srv, team_id, [{"agent_id": team_id, "role": "lead"}], lead=team_id)

    created = await client.post(
        "/api/team/runs",
        headers=auth,
        json={"team_agent_id": team_id, "goal": "lead-only 必须放行", "tier": "quick"},
    )
    assert created.status_code == 201, created.text
    run_id = str(created.json()["run_id"])

    rows = srv.services.team_run_repo.list_members(run_id)
    assert len(rows) == 1  # lead 是合法 roster 角色 —— 不得写成 `>= 2`
    assert rows[0].role == "lead"
    assert _table_counts(srv)["team_run_members"] == 1
