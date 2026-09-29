"""T-76 附带：`TaskCreateBody.id`（plan 的 `id?`）在 **HTTP 面**的往返覆盖。

**三问（本 run 新立的新文件判据，先自答）**：
* **关切面** = 调用方**自带 `id`** 的任务创建，在 HTTP 上的**往返**：能否原样落库、重复时怎样拒、不传时如何分配；
* **一致性** = 与**服务层语义**同口径 —— `infra/db/repos/project_tasks.py:314`
  「A caller-supplied id is honoured verbatim, and a collision is refused…」；
* **入口** = **经真实 HTTP 客户端**（`httpx.AsyncClient` over the real ASGI app），不直调服务层。

**为什么单独成文件**：`tests/integration/` 当时有他人在飞（`backend` 正在动该目录）⇒ 新文件**零写区重叠**。
**本文件不覆盖**：`tests/unit/agents/test_team_run_service.py:469/:512` 那两条是**服务层**用例（各自 docstring 已写明
"through the service"）⇒ 二者互补，**不重复**。
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from tests.support.auth import create_agent

TEAM_MEMBERS = 2


class _RoomGateway:
    def __init__(self, services: Any) -> None:
        from octop.infra.gateway.threads import ThreadRegistry

        self.thread_registry = ThreadRegistry(
            session_repo=services.session_repo, thread_repo=services.thread_repo
        )


@pytest.fixture
async def run_env(env: tuple[httpx.AsyncClient, Any, dict[str, str]]) -> tuple[Any, ...]:
    """Real ASGI app + a live team with a configured roster (self-contained).

    Kept in this file on purpose: `backend` was editing other `tests/integration`
    modules, so a new file keeps the write scope disjoint.
    """
    client, srv, auth = env
    members = [await create_agent(client, auth, name=f"m{i}") for i in range(TEAM_MEMBERS)]
    resp = await client.post(
        "/api/teams", headers=auth, json={"name": "ID Round Trip", "member_ids": members}
    )
    assert resp.status_code in (200, 201), resp.text
    team_id = str(resp.json().get("team_id") or resp.json()["agent_id"])
    roster = await client.put(
        f"/api/teams/{team_id}/roster",
        headers=auth,
        json={
            "members": [
                {"agent_id": members[0], "role": "backend"},
                {"agent_id": members[1], "role": "qa"},
            ],
            "clear_lead": True,
        },
    )
    assert roster.status_code == 200, roster.text
    return client, auth, team_id, srv


async def _new_run(client: httpx.AsyncClient, auth: dict[str, str], team_id: str) -> str:
    r = await client.post(
        "/api/team/runs",
        headers=auth,
        json={"team_agent_id": team_id, "goal": "id round trip", "tier": "quick"},
    )
    assert r.status_code == 201, r.text
    return str(r.json()["run_id"])


async def _task_count(client: httpx.AsyncClient, auth: dict[str, str], run_id: str) -> int:
    r = await client.get(f"/api/team/runs/{run_id}/state?section=tasks", headers=auth)
    assert r.status_code == 200, r.text
    return len(r.json().get("tasks") or [])


# ① 正向：自带 id 原样落库，且**读回**一致（不是只看创建响应）
async def test_a_caller_supplied_id_round_trips_over_http(
    run_env: tuple[Any, ...],
) -> None:
    client, auth, team_id, _srv = run_env
    run_id = await _new_run(client, auth, team_id)

    created = await client.post(
        f"/api/team/runs/{run_id}/tasks",
        headers=auth,
        json={"id": "CALLER01", "title": "自带 id", "owner": "backend"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["id"] == "CALLER01"

    # 读回：经 state 分节再看一次（避免"响应里对、库里不对"）
    listed = await client.get(f"/api/team/runs/{run_id}/state?section=tasks", headers=auth)
    ids = [str(t["id"]) for t in (listed.json().get("tasks") or [])]
    assert ids == ["CALLER01"], ids


# ② 重复 id：三样齐备（状态 + 码 + details.code + zh 消息）**并且**没有多写一行
async def test_a_duplicate_task_id_is_refused_and_writes_nothing(
    run_env: tuple[Any, ...],
) -> None:
    client, auth, team_id, _srv = run_env
    run_id = await _new_run(client, auth, team_id)
    zh = {"Accept-Language": "zh"}

    first = await client.post(
        f"/api/team/runs/{run_id}/tasks",
        headers=auth,
        json={"id": "DUP01", "title": "第一次", "owner": "backend"},
    )
    assert first.status_code == 201, first.text
    before = await _task_count(client, auth, run_id)

    again = await client.post(
        f"/api/team/runs/{run_id}/tasks",
        headers={**auth, **zh},
        json={"id": "DUP01", "title": "第二次", "owner": "backend"},
    )
    assert again.status_code == 409, again.text
    err = again.json()["error"]
    assert err["code"] == "TEAM_TASK_GRAPH_INVALID"
    assert err["details"]["code"] == "duplicate-id"
    assert "任务依赖图" in err["message"], err["message"]

    # ★ "拒绝"与"没写"是两件事 —— 计数必须没变
    assert await _task_count(client, auth, run_id) == before


# ③ 正对照：不传 id ⇒ 201，且服务端自己分配了一个非空 id（"可选"不是"必须"）
async def test_an_omitted_id_is_assigned_by_the_server(run_env: tuple[Any, ...]) -> None:
    client, auth, team_id, _srv = run_env
    run_id = await _new_run(client, auth, team_id)

    created = await client.post(
        f"/api/team/runs/{run_id}/tasks",
        headers=auth,
        json={"title": "服务端分配", "owner": "backend"},
    )
    assert created.status_code == 201, created.text
    assigned = created.json()["id"]
    assert isinstance(assigned, str) and assigned and assigned != "CALLER01"
