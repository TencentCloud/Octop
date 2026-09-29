"""T-23 · 确认门全生命周期，**走 HTTP**（挂起 → 呈现 → 决策 → 恢复；幂等拒绝；到顶升级）。

`T-23` 的验收第一条要求"确认门全生命周期（挂起/呈现/**恢复**/幂等拒绝/到顶升级）有
端到端断言"。既有的 `test_team_runs_api.py` 只覆盖了其中**一侧的一半** ——
"没有待决决策时 decide ⇒ 409"（`TEAM_DECISION_NOT_PENDING`）。本文件补齐**完整生命周期**，
且每一跳都断言**拒绝之后什么都没变**（"拒了但已经改了"不是门禁）。

## ⚠️ 一处诚实边界：**挂起只有服务层入口，没有 HTTP 路由**
`raise_decision()` 没有对应的 HTTP 端点（`team_runs.py` 的 16 条路由里没有它）——
决策由服务在门禁处**内部**抛起（G3 方案确认门 / G16 到顶升级）。所以本文件里
**"挂起"这一步调服务方法**，而**呈现（`GET /state`）、决策（`POST /decision`）、
恢复（`POST :resume`）、非法的拒绝**——全部走真实 HTTP。
这一分工是**被测对象的形状**决定的，不是本文件的取舍；若将来补上"手动挂起"端点，
这几条用例应改为走 HTTP。
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from octop.infra.gateway.threads import ThreadRegistry
from tests.support.auth import create_agent

TEAM_MEMBERS = 2


class _FakeWorkspace:
    """Same dict-backed stand-in the sibling integration file uses."""

    def __init__(self) -> None:
        self.files: dict[str, str] = {}

    def read_text(self, path: str, *, limit: int = 10_000_000) -> str | None:
        return self.files.get(str(path))

    def write_text(self, path: str, content: str, *, force: bool = False) -> None:
        self.files[str(path)] = content

    def exists(self, path: str) -> bool:
        return str(path) in self.files

    def list_dir(self, path: str = ".") -> list[Any]:
        """**Harness shape** — ``{"path": <workspace-relative>, "is_dir"}`` (T-79)."""
        prefix = "" if str(path) in {"", "."} else str(path).rstrip("/") + "/"
        return [
            {"path": n, "is_dir": False}
            for n in sorted(self.files)
            if n.startswith(prefix) and "/" not in n[len(prefix) :]
        ]


class _RoomGateway:
    """Just enough gateway for the room thread: a **real** ``ThreadRegistry``.

    ``TeamRunService`` reaches the gateway only through ``.thread_registry``
    (``_open_room``), so a real registry over the test's own DB is enough — the
    same shape the unit tests use as ``_StubGateway``.
    """

    def __init__(self, services: Any) -> None:
        self.thread_registry = ThreadRegistry(
            session_repo=services.session_repo,
            thread_repo=services.thread_repo,
        )


@pytest.fixture
async def run_env(
    env: tuple[httpx.AsyncClient, Any, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> tuple[httpx.AsyncClient, dict[str, str], str, Any]:
    """A team plus a run service bound to the workspace the router will use."""
    client, srv, auth = env
    members = [await create_agent(client, auth, name=f"member-{i}") for i in range(TEAM_MEMBERS)]
    resp = await client.post(
        "/api/teams", headers=auth, json={"name": "Decision Team", "member_ids": members}
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
    # ⚠️ The gateway matters: ``TeamRunService._open_room()`` returns ``None`` without
    # one, and a run with no room thread cannot park a decision at all
    # (``set_pending_decision`` returns False — "has no room thread to park a
    # decision on"). The sibling integration file never binds one, which is exactly
    # why the decision lifecycle was uncovered: its runs can never reach a pending
    # decision. Binding a registry is what makes this file able to test it at all.
    service.bind_runtime(
        gateway=_RoomGateway(srv.services),  # type: ignore[arg-type]
        workspace_for=lambda agent_id: workspace,
    )
    monkeypatch.setattr(type(srv.services), "team_run_service", lambda self: service)
    return client, auth, team_id, service


async def _create_run(
    client: httpx.AsyncClient, auth: dict[str, str], team_id: str, **overrides: Any
) -> dict[str, Any]:
    body = {"team_agent_id": team_id, "goal": "确认门生命周期", "tier": "quick", **overrides}
    resp = await client.post("/api/team/runs", headers=auth, json=body)
    assert resp.status_code == 201, resp.text
    return dict(resp.json())


async def _state(client: httpx.AsyncClient, auth: dict[str, str], run_id: str) -> dict[str, Any]:
    """The **detail** read — the one that carries ``pending_decision``.

    ⚠️ Deliberately not ``GET /{run_id}/state``: ``pending_decision`` lives on
    ``RunDetailOut`` (``GET /api/team/runs/{run_id}``, built by ``_detail``), while
    ``RunStateOut`` / ``/state`` carries only the progressive sections
    (summary/people/feed/artifacts/tasks/check). A client that polls ``/state``
    looking for a decision to resolve will never see one — worth knowing before
    wiring a dashboard to the wrong endpoint.
    """
    resp = await client.get(f"/api/team/runs/{run_id}", headers=auth)
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


def _error_code(resp: httpx.Response) -> str:
    return str(resp.json()["error"]["code"])


# ─────────────────────────────────────────────────────────────────────────────
# 完整生命周期：挂起 → 呈现 → 决策 → 恢复
# ─────────────────────────────────────────────────────────────────────────────


async def test_the_full_decision_lifecycle_over_http(
    run_env: tuple[httpx.AsyncClient, dict[str, str], str, Any],
) -> None:
    client, auth, team_id, service = run_env
    run = await _create_run(client, auth, team_id)
    run_id = run["run_id"]

    # ── 挂起（服务层入口；见模块 docstring 的边界说明）──────────────────────
    raised = service.raise_decision(
        run_id,
        kind="confirm",
        reason="方案确认门：等用户拍板",
        options=["approve", "revise"],
    )
    decision_id = str(raised["id"])

    # ── 呈现：HTTP /state 必须把待决决策暴露出来（否则前端无法拍板）────────
    parked = await _state(client, auth, run_id)
    pending = parked["pending_decision"]
    assert pending is not None, "挂起后 /state 必须呈现 pending_decision"
    assert pending["id"] == decision_id
    assert pending["status"] == "pending"
    assert pending["options"] == ["approve", "revise"]

    # ── 拒/放两侧之一：待决期间不得推进阶段（G3）────────────────────────────
    blocked = await client.post(
        f"/api/team/runs/{run_id}:advance", headers=auth, json={"to_phase": "implement"}
    )
    assert blocked.status_code == 409
    assert _error_code(blocked) == "TEAM_DECISION_PENDING"
    still = await _state(client, auth, run_id)
    assert still["phase"] == parked["phase"], "被拒的 advance 不得改动 phase"

    # ── 决策：走真实 HTTP ──────────────────────────────────────────────────
    decided = await client.post(
        f"/api/team/runs/{run_id}/decision",
        headers=auth,
        json={"decision_id": decision_id, "choice": "approve", "note": "同意"},
    )
    assert decided.status_code == 200, decided.text

    # ── 呈现：决策后 payload **不是被删掉，而是被标成 resolved**（见下文陷阱用例）
    after = await _state(client, auth, run_id)
    assert after["pending_decision"] is not None
    assert after["pending_decision"]["status"] == "resolved"
    assert after["pending_decision"]["choice"] == "approve"

    # ── 恢复：parked 的 run 回到 running ────────────────────────────────────
    resumed = await client.post(f"/api/team/runs/{run_id}:resume", headers=auth)
    assert resumed.status_code == 200, resumed.text


async def test_deciding_the_same_decision_twice_is_not_pending(
    run_env: tuple[httpx.AsyncClient, dict[str, str], str, Any],
) -> None:
    """**幂等拒绝**：同一个 decision_id 二次提交 ⇒ 409，且**第一次的结果不被回滚**。"""
    client, auth, team_id, service = run_env
    run = await _create_run(client, auth, team_id)
    run_id = run["run_id"]
    raised = service.raise_decision(
        run_id, kind="confirm", reason="拍板", options=["approve", "revise"]
    )
    decision_id = str(raised["id"])

    first = await client.post(
        f"/api/team/runs/{run_id}/decision",
        headers=auth,
        json={"decision_id": decision_id, "choice": "approve"},
    )
    assert first.status_code == 200

    second = await client.post(
        f"/api/team/runs/{run_id}/decision",
        headers=auth,
        json={"decision_id": decision_id, "choice": "revise"},
    )
    assert second.status_code == 409, "同一决策二次提交必须是 409"
    assert _error_code(second) == "TEAM_DECISION_NOT_PENDING"

    # 二次提交**不得**把已经拍好的结果改掉（payload 仍是第一次那个 resolved 结果）
    state = await _state(client, auth, run_id)
    assert state["pending_decision"]["status"] == "resolved"
    assert state["pending_decision"]["choice"] == "approve", "二次提交改了第一次的结果"


async def test_a_choice_outside_the_options_is_400_and_leaves_the_run_parked(
    run_env: tuple[httpx.AsyncClient, dict[str, str], str, Any],
) -> None:
    """非法选项 ⇒ 400；且**run 仍然停在门上**（拒了但顺手解决掉 = 门禁失效）。"""
    client, auth, team_id, service = run_env
    run = await _create_run(client, auth, team_id)
    run_id = run["run_id"]
    raised = service.raise_decision(
        run_id, kind="confirm", reason="拍板", options=["approve", "revise"]
    )
    decision_id = str(raised["id"])

    bad = await client.post(
        f"/api/team/runs/{run_id}/decision",
        headers=auth,
        json={"decision_id": decision_id, "choice": "maybe"},
    )
    assert bad.status_code == 400
    assert _error_code(bad) == "TEAM_DECISION_OPTION_INVALID"

    state = await _state(client, auth, run_id)
    assert state["pending_decision"] is not None, "非法选项不得把决策消费掉"
    assert state["pending_decision"]["status"] == "pending"


async def test_an_unknown_decision_id_is_refused(
    run_env: tuple[httpx.AsyncClient, dict[str, str], str, Any],
) -> None:
    """待决的是 d1，却提交 d9 ⇒ 同样是 not-pending（不得"顺手"解决 d1）。"""
    client, auth, team_id, service = run_env
    run = await _create_run(client, auth, team_id)
    run_id = run["run_id"]
    service.raise_decision(run_id, kind="confirm", reason="拍板", options=["approve"])

    wrong = await client.post(
        f"/api/team/runs/{run_id}/decision",
        headers=auth,
        json={"decision_id": "not-the-pending-one", "choice": "approve"},
    )
    assert wrong.status_code == 409
    assert _error_code(wrong) == "TEAM_DECISION_NOT_PENDING"

    state = await _state(client, auth, run_id)
    assert state["pending_decision"] is not None


# ─────────────────────────────────────────────────────────────────────────────
# 到顶升级路径：G16 的 escalate 决策
# ─────────────────────────────────────────────────────────────────────────────


async def test_the_escalation_decision_parks_the_run_and_is_visible_over_http(
    run_env: tuple[httpx.AsyncClient, dict[str, str], str, Any],
) -> None:
    """**到顶升级**的形态：`kind="escalate"` 的决策必须和普通确认门**一样**挡住推进，
    并且经 HTTP 可见（前端要能用同一套 UI 呈现"升级用户裁决"）。

    这里走服务层抛起（同"挂起"的边界说明）；关键在于**它经 HTTP 呈现、且确实阻断**。
    """
    client, auth, team_id, service = run_env
    run = await _create_run(client, auth, team_id)
    run_id = run["run_id"]

    raised = service.raise_decision(
        run_id,
        kind="escalate",
        reason="同一问题连续两轮未闭环",
        options=["continue", "stop"],
    )

    state = await _state(client, auth, run_id)
    pending = state["pending_decision"]
    assert pending is not None
    assert pending["kind"] == "escalate"
    assert pending["id"] == raised["id"]

    blocked = await client.post(
        f"/api/team/runs/{run_id}:advance", headers=auth, json={"to_phase": "implement"}
    )
    assert blocked.status_code == 409
    assert _error_code(blocked) == "TEAM_DECISION_PENDING"

    # 放行侧：升级裁决拍完后，决策门不再阻断（phase 可能仍被别的门挡，但**码不同**）
    await client.post(
        f"/api/team/runs/{run_id}/decision",
        headers=auth,
        json={"decision_id": raised["id"], "choice": "continue"},
    )
    cleared = await _state(client, auth, run_id)
    assert cleared["pending_decision"]["status"] == "resolved"
    assert cleared["pending_decision"]["choice"] == "continue"

    after = await client.post(
        f"/api/team/runs/{run_id}:advance", headers=auth, json={"to_phase": "implement"}
    )
    if after.status_code == 409:
        assert _error_code(after) != "TEAM_DECISION_PENDING", (
            "决策已拍完，仍是 DECISION_PENDING ⇒ 决策门没有真正放行"
        )


# ─────────────────────────────────────────────────────────────────────────────
# ★ 一条会被前端踩到的契约：决策**不会被移除**，只会被标成 resolved
# ─────────────────────────────────────────────────────────────────────────────


async def test_a_decided_payload_stays_on_the_run_marked_resolved(
    run_env: tuple[httpx.AsyncClient, dict[str, str], str, Any],
) -> None:
    """**端到端钉住这条契约**：`pending_decision` 一旦被抛起就**再也不会变回 None**，
    拍板后它是 ``status="resolved"`` 的那个 payload（仍带 choice/note/resolved_at）。

    ⇒ 判"还有没有待拍板的事"**必须看 ``status == "pending"``**，不能看"这个字段在不在"。
    只写 ``if pending_decision: 显示确认按钮`` 的前端会**永远**显示确认按钮。
    这条陷阱没有任何既有用例覆盖（既有文件只测了"没有决策时 decide ⇒ 409"）。
    """
    client, auth, team_id, service = run_env
    run = await _create_run(client, auth, team_id)
    run_id = run["run_id"]

    before = await _state(client, auth, run_id)
    assert before["pending_decision"] is None, "全新 run 上不应有待决 payload"

    raised = service.raise_decision(
        run_id, kind="confirm", reason="拍板", options=["approve", "revise"]
    )
    assert (await _state(client, auth, run_id))["pending_decision"]["status"] == "pending"

    await client.post(
        f"/api/team/runs/{run_id}/decision",
        headers=auth,
        json={"decision_id": raised["id"], "choice": "approve", "note": "备注"},
    )

    after = await _state(client, auth, run_id)
    payload = after["pending_decision"]
    assert payload is not None, "拍板后 payload 仍在（这是契约，不是缺陷）"
    assert payload["status"] == "resolved"
    assert payload["choice"] == "approve"
    assert payload["note"] == "备注"
    assert payload["resolved_at"] > 0
