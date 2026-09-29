"""T6 · 计划门 + 搁浅上报的 **HTTP 面**（真路由 · 真 DB · 真拒绝码）。

权威 = `team/2026-09-29-234500/PLAN.md` §2.3（模型字段）/ §2.4（拒绝码与状态）/
§3（写入矩阵）/ §4.4（A2 落点）＋ `SPEC.md` §5.3-⑩ / §5.4 边界表。

本文件覆盖 4 条**写路由**与 3 处**只加字段**：

| 面 | 断言要点 |
|---|---|
| `POST /{run_id}:plan` | 200 回 `draft`；`pending_decision.draft.planStatus=staged`；非法草稿 **422** `TEAM_PLAN_DRAFT_INVALID` 且不落草稿 |
| `POST /{run_id}:approve` | 200 回 `tasks` ＋ `settledKept`；草稿键被清；无草稿/重复 ⇒ **409** `TEAM_PLAN_DRAFT_MISSING` |
| `POST /{run_id}:discard` | 200 回 `discarded{at,reason,taskCount}`；重复 ⇒ **409**；终态 run ⇒ **409** `TEAM_RUN_TERMINAL` |
| `POST /{run_id}:settle` | 200 回 `settled`；空集 ⇒ `[]` 且**不写盘**；`check.stranded` 随之归零；旧 token 仍 409 `TEAM_ATTEMPT_STALE` |
| `GET /{run_id}/check` | ★ **只加字段、不加违规码**：`violations` 逐字不变；`stranded` 只含 `count/ids/reasons` |
| `RunSummaryOut` / `:resume` | `strandedCount` 出现在响应里；`:resume` 不回写任务行 |

**仅本地可观测**：全部经 `httpx` 打真实路由（无 mock 路由层），断言对象是本进程的临时
`OCTOP_HOME`（`tmp_octop_home`）—— 不触网、不碰用户目录、不启第二个服务。
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from octop.api.app import build_app
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.utils.ulid import new_short_id
from tests.support.auth import create_agent, create_user

TEAM_MEMBERS = 2
SCOPE = "src/octop/api/routers/team_runs.py"


class _FakeWorkspace:
    """Same dict-backed stand-in the sibling integration files use."""

    def __init__(self) -> None:
        self.files: dict[str, str] = {}

    def read_text(self, path: str, *, limit: int = 10_000_000) -> str | None:
        return self.files.get(str(path))

    def write_text(self, path: str, content: str, *, force: bool = False) -> None:
        self.files[str(path)] = content

    def exists(self, path: str) -> bool:
        return str(path) in self.files

    def list_dir(self, path: str = ".") -> list[Any]:
        prefix = "" if str(path) in {"", "."} else str(path).rstrip("/") + "/"
        return [
            {"path": n, "is_dir": False}
            for n in sorted(self.files)
            if n.startswith(prefix) and "/" not in n[len(prefix) :]
        ]


class _RoomGateway:
    """Just enough gateway for the room thread: a **real** ``ThreadRegistry``.

    ``set_pending_decision`` needs a room thread, so without this the plan gate
    cannot park anything at all (the ``R2`` path returns ``False`` instead).
    """

    def __init__(self, services: Any) -> None:
        self.thread_registry = ThreadRegistry(
            session_repo=services.session_repo, thread_repo=services.thread_repo
        )


@pytest.fixture
async def gate_env(
    env: tuple[httpx.AsyncClient, Any, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> tuple[httpx.AsyncClient, dict[str, str], dict[str, str], str, Any, Any]:
    """Team **owned by a regular user** + the run service the router resolves.

    The owner has to be a non-admin: ``assert_agent_owner`` lets an admin through every
    run on the box, so an admin-owned team could never show the越权 boundary. The team,
    its members and the runs are therefore all created as ``owner`` — exactly what a
    real non-admin caller sees.
    """
    client, srv, admin = env
    owner = await create_user(client, admin, username=f"gate-{new_short_id()}")
    outsider = await create_user(client, admin, username=f"gate-other-{new_short_id()}")
    members = [await create_agent(client, owner, name=f"gate-member-{i}") for i in range(2)]
    resp = await client.post(
        "/api/teams", headers=owner, json={"name": "Plan Gate Team", "member_ids": members}
    )
    assert resp.status_code in (200, 201), resp.text
    team_id = str(resp.json()["agent_id"])

    workspace = _FakeWorkspace()
    workspace.write_text(
        ".octop/manifest.json",
        json.dumps(
            {
                "members": [
                    {"agent_id": team_id, "role": "lead"},
                    {"agent_id": members[0], "role": "backend"},
                    {"agent_id": members[1], "role": "qa"},
                ]
            }
        ),
    )
    service = srv.services.team_run_service()
    # ``SharedServices.team_run_service()`` is memoised, so the instance bound here is
    # the very one the routes resolve — no stand-in patch, no route-layer stub.
    service.bind_runtime(  # type: ignore[call-arg]
        gateway=_RoomGateway(srv.services),
        workspace_for=lambda agent_id: workspace,
    )
    monkeypatch.setattr(type(srv.services), "team_run_service", lambda self: service)
    return client, owner, outsider, team_id, service, srv


def _code(resp: httpx.Response) -> str:
    return str(resp.json()["error"]["code"])


async def _create_run(client: httpx.AsyncClient, auth: dict[str, str], team_id: str) -> str:
    resp = await client.post(
        "/api/team/runs",
        headers=auth,
        json={"team_agent_id": team_id, "goal": "计划门与搁浅", "tier": "standard"},
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["run_id"])


async def _add_task(
    client: httpx.AsyncClient, auth: dict[str, str], run_id: str, *, title: str, owner: str
) -> dict[str, Any]:
    resp = await client.post(
        f"/api/team/runs/{run_id}/tasks",
        headers=auth,
        json={
            "id": f"t-{new_short_id()}",
            "title": title,
            "kind": "work",
            "owner": owner,
            "inScope": [SCOPE],
            "verify": ["pytest -q"],
        },
    )
    assert resp.status_code == 201, resp.text
    return dict(resp.json())


async def _rows(client: httpx.AsyncClient, auth: dict[str, str], run_id: str) -> dict[str, Any]:
    resp = await client.get(f"/api/team/runs/{run_id}/tasks", headers=auth)
    assert resp.status_code == 200, resp.text
    return {
        str(node["id"]): (node["status"], node["attempt"], node["attemptId"])
        for node in resp.json()["nodes"]
    }


async def _settle_one_task(
    client: httpx.AsyncClient, auth: dict[str, str], run_id: str, task: dict[str, Any]
) -> None:
    """Drive one task into a settled state through the **real** HTTP ops.

    ``claim`` stores the attempt token; ``fail`` then blocks the task, which is one of
    the three settled statuses ``:approve`` keeps verbatim (``done`` / ``blocked`` /
    ``cancelled``). The task is deliberately settled via a different op than ``:approve``
    itself, so the merge is what keeps it — not this helper.
    """
    url = f"/api/team/runs/{run_id}/tasks/{task['id']}"
    claimed = await client.patch(url, headers=auth, json={"attemptId": "", "op": "claim"})
    assert claimed.status_code == 200, claimed.text
    token = str(claimed.json()["attemptId"])
    failed = await client.patch(
        url, headers=auth, json={"attemptId": token, "op": "fail", "role": "qa"}
    )
    assert failed.status_code == 200, failed.text
    assert failed.json()["status"] == "blocked"


def _draft(*task_ids: str, owner: str = "backend") -> dict[str, Any]:
    return {
        "roles": ["lead", "backend", "qa"],
        "tasks": [
            {
                "id": task_id,
                "title": f"草稿任务 {task_id}",
                "owner": owner,
                "inScope": [SCOPE],
                "verify": ["pytest -q"],
            }
            for task_id in task_ids
        ],
    }


async def _feed(
    client: httpx.AsyncClient, auth: dict[str, str], run_id: str, team_id: str
) -> list[Any]:
    """The run's timeline projection — the only other thing a stray write would move."""
    resp = await client.get(
        f"/api/team/runs/{run_id}/state", headers=auth, params={"section": "feed"}
    )
    assert resp.status_code == 200, resp.text
    assert team_id  # the section is team-scoped; keeping the id documents that
    return list(resp.json()["feed"])


async def _check_section(
    client: httpx.AsyncClient, auth: dict[str, str], run_id: str
) -> dict[str, Any]:
    """The **other** check surface: `GET /state?section=check` (progressive loading).

    Both surfaces build a ``CheckOut``, so "field, not violation code" has to hold on
    each of them — asserting only ``/check`` would leave the `/state` copy unguarded.
    """
    resp = await client.get(
        f"/api/team/runs/{run_id}/state", headers=auth, params={"section": "check"}
    )
    assert resp.status_code == 200, resp.text
    return dict(resp.json()["check"])


def _strand(service: Any, task_id: str) -> str:
    """Put **another generation's** token on the row and move it to ``doing``.

    Legal without reaching into a repo from the test: the routes read the task through
    this same service, so the row is genuinely stranded from the route's point of view
    — including the ``epoch`` reason, because ``bind_runtime`` minted this generation.
    """
    token = "previousboot.0001"
    assert service._tasks.claim(
        task_id, claimed_by="backend", expected_attempt_id=None, attempt_id=token
    )
    service._tasks.update(task_id, status="doing")
    return token


# ── A1：草稿门 ───────────────────────────────────────────────────────────────


async def test_plan_draft_is_staged_inside_the_pending_decision(
    gate_env: tuple[httpx.AsyncClient, dict[str, str], dict[str, str], str, Any, Any],
) -> None:
    """`:plan` 成功后草稿挂在 `pending_decision` 里（R2 路径），且门确实合上。"""
    client, auth, _outsider, team_id, _service, _srv = gate_env
    run_id = await _create_run(client, auth, team_id)

    staged = await client.post(
        f"/api/team/runs/{run_id}:plan", headers=auth, json={"draft": _draft("d-1", "d-2")}
    )
    assert staged.status_code == 200, staged.text
    assert staged.json()["draft"]["planStatus"] == "staged"
    assert [t["id"] for t in staged.json()["draft"]["tasks"]] == ["d-1", "d-2"]

    detail = await client.get(f"/api/team/runs/{run_id}", headers=auth)
    assert detail.status_code == 200, detail.text
    pending = detail.json()["pending_decision"]
    assert pending["status"] == "pending"
    assert [t["id"] for t in pending["draft"]["tasks"]] == ["d-1", "d-2"]

    # 真门：草稿未批 ⇒ advance 必须 409（假门就是这里不红）
    blocked = await client.post(
        f"/api/team/runs/{run_id}:advance", headers=auth, json={"to_phase": "implement"}
    )
    assert blocked.status_code == 409
    assert _code(blocked) == "TEAM_DECISION_PENDING"


async def test_invalid_draft_is_422_and_stages_nothing(
    gate_env: tuple[httpx.AsyncClient, dict[str, str], dict[str, str], str, Any, Any],
) -> None:
    """B1/B3：owner 不在 roles ⇒ **422** `TEAM_PLAN_DRAFT_INVALID`，草稿零残留。"""
    client, auth, _outsider, team_id, _service, _srv = gate_env
    run_id = await _create_run(client, auth, team_id)

    refused = await client.post(
        f"/api/team/runs/{run_id}:plan",
        headers=auth,
        json={"draft": _draft("d-1", owner="nobody")},
    )
    assert refused.status_code == 422, refused.text
    assert _code(refused) == "TEAM_PLAN_DRAFT_INVALID"
    assert refused.json()["error"]["details"]["code"] == "owner-not-in-roles"

    detail = await client.get(f"/api/team/runs/{run_id}", headers=auth)
    assert detail.json()["pending_decision"] is None, "被拒的草稿不得留下决策"


async def test_approve_writes_tasks_keeps_settled_and_clears_the_draft(
    gate_env: tuple[httpx.AsyncClient, dict[str, str], dict[str, str], str, Any, Any],
) -> None:
    """`:approve` = 合并写：settled 保留、其余被草稿取代、草稿键清空。"""
    client, auth, _outsider, team_id, _service, _srv = gate_env
    run_id = await _create_run(client, auth, team_id)
    settled = await _add_task(client, auth, run_id, title="已结算", owner="qa")
    superseded = await _add_task(client, auth, run_id, title="将被取代", owner="backend")
    await _settle_one_task(client, auth, run_id, settled)

    staged = await client.post(
        f"/api/team/runs/{run_id}:plan", headers=auth, json={"draft": _draft("d-1")}
    )
    assert staged.status_code == 200, staged.text
    approved = await client.post(f"/api/team/runs/{run_id}:approve", headers=auth)
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert [t["id"] for t in body["tasks"]] == ["d-1"]
    assert body["settledKept"] == [settled["id"]]

    after = await _rows(client, auth, run_id)
    assert set(after) == {settled["id"], "d-1"}
    assert superseded["id"] not in after
    detail = await client.get(f"/api/team/runs/{run_id}", headers=auth)
    assert detail.json()["pending_decision"]["status"] == "resolved"
    assert "draft" not in detail.json()["pending_decision"]

    again = await client.post(f"/api/team/runs/{run_id}:approve", headers=auth)
    assert again.status_code == 409
    assert _code(again) == "TEAM_PLAN_DRAFT_MISSING"


async def test_discard_cancels_the_decision_and_repeat_is_409(
    gate_env: tuple[httpx.AsyncClient, dict[str, str], dict[str, str], str, Any, Any],
) -> None:
    """B4/⑤：`:discard` 记录 `discarded{at,reason,taskCount}`；重复 ⇒ 409。"""
    client, auth, _outsider, team_id, _service, _srv = gate_env
    run_id = await _create_run(client, auth, team_id)
    staged = await client.post(
        f"/api/team/runs/{run_id}:plan", headers=auth, json={"draft": _draft("d-1", "d-2")}
    )
    assert staged.status_code == 200, staged.text

    dropped = await client.post(
        f"/api/team/runs/{run_id}:discard", headers=auth, json={"reason": "范围变了"}
    )
    assert dropped.status_code == 200, dropped.text
    discarded = dropped.json()["draft"]["discarded"]
    assert discarded["taskCount"] == 2
    assert discarded["reason"] == "范围变了"
    assert isinstance(discarded["at"], int)

    detail = await client.get(f"/api/team/runs/{run_id}", headers=auth)
    pending = detail.json()["pending_decision"]
    assert pending["status"] == "cancelled"
    assert "draft" not in pending

    repeat = await client.post(f"/api/team/runs/{run_id}:discard", headers=auth, json={})
    assert repeat.status_code == 409
    assert _code(repeat) == "TEAM_PLAN_DRAFT_MISSING"


async def test_terminal_run_refuses_all_four_write_routes(
    gate_env: tuple[httpx.AsyncClient, dict[str, str], dict[str, str], str, Any, Any],
) -> None:
    """B7/③：终态 run 上 4 条写路由全部 **409** `TEAM_RUN_TERMINAL`，且状态零变更。"""
    client, auth, _outsider, team_id, _service, _srv = gate_env
    run_id = await _create_run(client, auth, team_id)
    cancelled = await client.post(f"/api/team/runs/{run_id}:cancel", headers=auth)
    assert cancelled.status_code == 200, cancelled.text

    calls = [
        (f"/api/team/runs/{run_id}:plan", {"draft": _draft("d-1")}),
        (f"/api/team/runs/{run_id}:approve", {}),
        (f"/api/team/runs/{run_id}:discard", {}),
        (f"/api/team/runs/{run_id}:settle", {}),
    ]
    for url, body in calls:
        resp = await client.post(url, headers=auth, json=body)
        assert resp.status_code == 409, (url, resp.text)
        assert _code(resp) == "TEAM_RUN_TERMINAL", (url, resp.text)

    still = await client.get(f"/api/team/runs/{run_id}", headers=auth)
    assert still.json()["status"] == "cancelled"
    assert still.json()["pending_decision"] is None


async def test_another_user_cannot_see_or_write_the_run(
    gate_env: tuple[httpx.AsyncClient, dict[str, str], dict[str, str], str, Any, Any],
) -> None:
    """B6/④：非 owner（也非 admin）⇒ **403**，4 条写路由一条都不成功。

    ⚠️ 与 `SPEC §5.3-④` 的登记差异：`_require_owned_run` @456 走
    `assert_agent_owner`（403 `FORBIDDEN`），**不是** SPEC 写的 404。既有的
    `test_team_runs_api.py::test_a_run_is_invisible_to_another_user` 同样断言 403，
    即这是一个已在册的既有语义差，不是本卡引入。真 404 只有 run 不存在时出现
    （`TEAM_RUN_NOT_FOUND`，见下一条用例）。
    """
    client, auth, outsider, team_id, _service, _srv = gate_env
    run_id = await _create_run(client, auth, team_id)

    for url, body in [
        (f"/api/team/runs/{run_id}:plan", {"draft": _draft("d-1")}),
        (f"/api/team/runs/{run_id}:approve", {}),
        (f"/api/team/runs/{run_id}:discard", {}),
        (f"/api/team/runs/{run_id}:settle", {}),
    ]:
        resp = await client.post(url, headers=outsider, json=body)
        assert resp.status_code == 403, (url, resp.text)
        assert _code(resp) == "FORBIDDEN", (url, resp.text)

    unknown = await client.post(
        "/api/team/runs/no-such-run:plan", headers=auth, json={"draft": _draft("d-1")}
    )
    assert unknown.status_code == 404
    assert _code(unknown) == "TEAM_RUN_NOT_FOUND"


# ── A2：只报不动 + 显式 settle ───────────────────────────────────────────────


async def test_check_adds_the_stranded_field_without_touching_violations(
    gate_env: tuple[httpx.AsyncClient, dict[str, str], dict[str, str], str, Any, Any],
) -> None:
    """★ B14/`AC-A2-2`：`violations` 逐字不变；搁浅只出现在**新字段**里；不写盘。"""
    client, auth, _outsider, team_id, service, _srv = gate_env
    run_id = await _create_run(client, auth, team_id)
    task = await _add_task(client, auth, run_id, title="被上一代占住", owner="backend")

    first = await client.get(f"/api/team/runs/{run_id}/check", headers=auth)
    assert first.status_code == 200, first.text
    violations_before = list(first.json()["violations"])
    assert first.json()["stranded"] == {"count": 0, "ids": [], "reasons": []}

    # 先造出搁浅，**再**取快照 —— 否则「check 不写盘」会被本用例自己的写弄假。
    _strand(service, str(task["id"]))
    rows_before = await _rows(client, auth, run_id)
    feed_before = await _feed(client, auth, run_id, team_id)

    second = await client.get(f"/api/team/runs/{run_id}/check", headers=auth)
    assert second.status_code == 200, second.text
    body = second.json()
    # 只加字段：既有违规数组逐字相同（历史 run 不会因为搁浅变红）
    assert body["violations"] == violations_before
    assert body["finding_reopened"] == first.json()["finding_reopened"]
    assert body["stranded"] == {
        "count": 1,
        "ids": [task["id"]],
        "reasons": ["epoch"],
    }
    assert "stranded" not in body["violations"]
    assert await _rows(client, auth, run_id) == rows_before, "GET /check 不得写盘"
    assert await _feed(client, auth, run_id, team_id) == feed_before, "GET /check 不得记时间线"

    # 另一个 check 面（`/state?section=check`）必须同语义：字段同值、违规同集。
    section = await _check_section(client, auth, run_id)
    assert section["violations"] == violations_before
    assert section["stranded"] == body["stranded"]


async def test_settle_rearms_the_selected_task_and_check_goes_quiet(
    gate_env: tuple[httpx.AsyncClient, dict[str, str], dict[str, str], str, Any, Any],
) -> None:
    """B15/`AC-A2-3`：`:settle` 把搁浅行重新武装；空集 ⇒ `[]` 且不写盘。"""
    client, auth, _outsider, team_id, service, _srv = gate_env
    run_id = await _create_run(client, auth, team_id)
    first = await _add_task(client, auth, run_id, title="搁浅一", owner="backend")
    second = await _add_task(client, auth, run_id, title="搁浅二", owner="qa")
    old_token = _strand(service, str(first["id"]))
    _strand(service, str(second["id"]))

    settled = await client.post(
        f"/api/team/runs/{run_id}:settle",
        headers=auth,
        json={"taskIds": [first["id"]], "reason": "进程重启"},
    )
    assert settled.status_code == 200, settled.text
    assert settled.json()["settled"] == [first["id"]]

    rearmed = (await _rows(client, auth, run_id))[str(first["id"])]
    assert rearmed[0] == "todo"
    assert rearmed[1] == 2, "settle 必须是 attempt + 1（`_strand` 本身不推进 attempt）"
    assert rearmed[2] != old_token
    assert rearmed[2].startswith(service._runtime_epoch + "."), "新 token 必须带本代 epoch"

    after = await client.get(f"/api/team/runs/{run_id}/check", headers=auth)
    assert after.json()["stranded"]["ids"] == [second["id"]], "未被选中的行不得被清算"

    # ② 全部清算 ⇒ 无可清算 ⇒ `200 {"settled": []}`（**不**新增「无搁浅」拒绝码）且不写盘
    rest = await client.post(f"/api/team/runs/{run_id}:settle", headers=auth, json={})
    assert rest.status_code == 200, rest.text
    assert rest.json() == {"settled": [second["id"]]}

    before = await _rows(client, auth, run_id)
    quiet = await client.get(f"/api/team/runs/{run_id}/check", headers=auth)
    assert quiet.json()["stranded"] == {"count": 0, "ids": [], "reasons": []}
    empty = await client.post(f"/api/team/runs/{run_id}:settle", headers=auth, json={})
    assert empty.status_code == 200, empty.text
    assert empty.json() == {"settled": []}
    assert await _rows(client, auth, run_id) == before, "空集不得写盘"

    # 旧 attempt token 仍然迟到写被拒（settle 没有把 G8 拆掉）
    stale = await client.patch(
        f"/api/team/runs/{run_id}/tasks/{first['id']}",
        headers=auth,
        json={"attemptId": old_token, "op": "report", "role": "backend"},
    )
    assert stale.status_code == 409
    assert _code(stale) == "TEAM_ATTEMPT_STALE"


async def test_resume_reports_the_stranded_count_without_settling(
    gate_env: tuple[httpx.AsyncClient, dict[str, str], dict[str, str], str, Any, Any],
) -> None:
    """`AC-A2-5`/B13：`:resume` **回报** `strandedCount`，但绝不自动清算（B13）。"""
    client, auth, _outsider, team_id, service, _srv = gate_env
    run_id = await _create_run(client, auth, team_id)
    task = await _add_task(client, auth, run_id, title="重启后搁浅", owner="backend")

    clean = await client.post(f"/api/team/runs/{run_id}:resume", headers=auth)
    assert clean.status_code == 200, clean.text
    assert clean.json()["strandedCount"] == 0

    _strand(service, str(task["id"]))
    rows_before = await _rows(client, auth, run_id)

    resumed = await client.post(f"/api/team/runs/{run_id}:resume", headers=auth)
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["strandedCount"] == 1
    # 既有 13 个键逐字不变（只加字段）
    assert set(clean.json()) == set(resumed.json())
    assert await _rows(client, auth, run_id) == rows_before, "resume 不得隐式 settle"


async def test_run_summary_and_openapi_expose_the_new_typed_fields(
    gate_env: tuple[httpx.AsyncClient, dict[str, str], dict[str, str], str, Any, Any],
) -> None:
    """`RunSummaryOut.strandedCount` 在列表响应里；4 条新路由有 typed `response_model`。"""
    client, auth, _outsider, team_id, _service, srv = gate_env
    run_id = await _create_run(client, auth, team_id)

    listed = await client.get(f"/api/team/runs?team_id={team_id}", headers=auth)
    assert listed.status_code == 200, listed.text
    summary = next(row for row in listed.json() if row["run_id"] == run_id)
    assert summary["strandedCount"] == 0

    # `/api/openapi.json` 默认关闭（`test_scalar.py::test_api_docs_disabled_by_default`），
    # 所以这里直接向**同一个** server 取 app 的 schema，而不是另开一个服务。
    spec = build_app(srv).openapi()
    operations = {
        ":plan": "PlanDraftOut",
        ":approve": "PlanApproveOut",
        ":discard": "PlanDraftOut",
        ":settle": "SettleOut",
    }
    for verb, model in operations.items():
        op = spec["paths"][f"/api/team/runs/{{run_id}}{verb}"]["post"]
        assert op["summary"], (verb, "缺少 summary")
        assert op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
            f"/{model}"
        ), (verb, model)
    assert spec["paths"]["/api/team/runs/{run_id}/check"]["get"]["summary"]
    assert "stranded" in spec["components"]["schemas"]["CheckOut"]["properties"]
    stranded_count = spec["components"]["schemas"]["RunSummaryOut"]["properties"]["strandedCount"]
    assert stranded_count["type"] == "integer"
    assert stranded_count["default"] == 0
