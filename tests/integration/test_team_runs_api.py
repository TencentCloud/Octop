"""``/api/team/runs/*`` — the HTTP face of the run lifecycle.

This file is T-16's own verify target, so it is written to prove **wiring**, not
service behaviour (that is ``tests/unit/agents/test_team_run_service.py``):

* every route answers over real HTTP with the declared shape;
* the gates are reachable *through* the routes (a refused advance is a 409 with the
  plan's code, not a 500 and not a silent success);
* the runtime seam works: binding a workspace through
  ``SharedServices.team_run_service().bind_runtime(...)`` makes the artifact routes
  and the phase gates live — which is what T-17 will do for real.

The agent turn behind ``persist`` dispatch is **not** exercised here (no provider on
this machine); the dispatch route is covered for its one-shot channel, which starts
no room turn by design.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from tests.support.auth import create_agent, create_user

TEAM_MEMBERS = 2
FILLED_SPEC = "# SPEC\n\n## 边界与禁止项\n\n| 边界 | 处置 |\n| --- | --- |\n| 无 | 无 |\n"


class _FakeWorkspace:
    """Dict-backed ``BackendWorkspace`` stand-in (same shape the unit tests use)."""

    def __init__(self) -> None:
        self.files: dict[str, str] = {}

    def read_text(self, path: str, *, limit: int = 10_000_000) -> str | None:
        return self.files.get(str(path))

    def write_text(self, path: str, content: str, *, force: bool = False) -> None:
        self.files[str(path)] = content

    def exists(self, path: str) -> bool:
        return str(path) in self.files

    def list_dir(self, path: str = ".") -> list[Any]:
        """**Harness shape** — ``{"path": <workspace-relative>, "is_dir"}`` (T-79).

        This double used to hand back an object with a basename-only ``.name``, i.e. it
        was built to match ``present_artifacts``' *assumption* instead of the real
        ``BackendWorkspace.list_dir`` contract ⇒ every ``list_dir``-dependent assertion in
        this file could only ever pass (the T-72 mechanism).
        """
        prefix = "" if str(path) in {"", "."} else str(path).rstrip("/") + "/"
        out: list[Any] = []
        for name in sorted(self.files):
            if name.startswith(prefix) and "/" not in name[len(prefix) :]:
                out.append({"path": name, "is_dir": False})
        return out


@pytest.fixture
async def run_env(
    env: tuple[httpx.AsyncClient, Any, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> tuple[httpx.AsyncClient, dict[str, str], str, Any]:
    """A team, and the *production* run service bound to a workspace the router uses.

    ``SharedServices.team_run_service()`` is memoised (T-67), so the instance bound here
    is the very one the routes resolve -- the same shape as the server's boot. The
    stand-in patch this fixture used to install is gone: a substitute would have kept
    supplying the missing link, so the routes could fall back to an unbound service and
    these tests would still be green.
    """
    client, srv, auth = env
    members = [await create_agent(client, auth, name=f"member-{i}") for i in range(TEAM_MEMBERS)]
    resp = await client.post(
        "/api/teams", headers=auth, json={"name": "Run Team", "member_ids": members}
    )
    assert resp.status_code in (200, 201), resp.text
    team_id = str(resp.json()["agent_id"])

    workspace = _FakeWorkspace()
    # The roster's sole authority is the manifest; roles drive the tier trim.
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
    # The routes must get *this* object (and its bound runtime) with no patching at all.
    assert srv.services.team_run_service() is service
    service.bind_runtime(workspace_for=lambda agent_id: workspace)
    return client, auth, team_id, service


async def _create_run(
    client: httpx.AsyncClient, auth: dict[str, str], team_id: str, **overrides: Any
) -> dict[str, Any]:
    body = {"team_agent_id": team_id, "goal": "把看板做完", "tier": "quick", **overrides}
    resp = await client.post("/api/team/runs", headers=auth, json=body)
    assert resp.status_code == 201, resp.text
    return dict(resp.json())


# ── the routes answer, typed, with the plan's shapes ─────────────────────────


async def test_create_run_returns_the_plan_shape(
    run_env: tuple[httpx.AsyncClient, dict[str, str], str, Any],
) -> None:
    client, auth, team_id, _service = run_env

    run = await _create_run(client, auth, team_id)

    assert run["team_agent_id"] == team_id
    assert run["tier"] == "quick"
    assert run["status"] == "running"
    assert run["phase"] == "clarify"
    # quick tier = four phases, seq reordered by the service
    assert [p["phase"] for p in run["phases"]] == ["clarify", "implement", "test", "deliver"]
    assert [p["seq"] for p in run["phases"]] == [0, 1, 2, 3]
    assert run["allowed_phases"] == ["implement"]


async def test_list_and_detail_are_owned_by_the_team_owner(
    run_env: tuple[httpx.AsyncClient, dict[str, str], str, Any],
) -> None:
    client, auth, team_id, _service = run_env
    run = await _create_run(client, auth, team_id)

    listed = await client.get("/api/team/runs", headers=auth, params={"team_id": team_id})
    assert listed.status_code == 200
    assert [item["run_id"] for item in listed.json()] == [run["run_id"]]

    detail = await client.get(f"/api/team/runs/{run['run_id']}", headers=auth)
    assert detail.status_code == 200
    assert detail.json()["run_id"] == run["run_id"]
    assert detail.json()["members"]  # roster came from the manifest

    assert (await client.get("/api/team/runs/nope", headers=auth)).status_code == 404


async def test_a_run_is_invisible_to_another_user(
    run_env: tuple[httpx.AsyncClient, dict[str, str], str, Any],
) -> None:
    client, auth, team_id, _service = run_env
    run = await _create_run(client, auth, team_id)
    other_auth = await create_user(client, auth, username="outsider")

    resp = await client.get(f"/api/team/runs/{run['run_id']}", headers=other_auth)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_state_sections_are_progressive(
    run_env: tuple[httpx.AsyncClient, dict[str, str], str, Any],
) -> None:
    client, auth, team_id, _service = run_env
    run = await _create_run(client, auth, team_id)

    people = await client.get(
        f"/api/team/runs/{run['run_id']}/state", headers=auth, params={"section": "people"}
    )
    assert people.status_code == 200
    assert people.json()["section"] == "people"
    assert people.json()["members"]

    feed = await client.get(
        f"/api/team/runs/{run['run_id']}/state", headers=auth, params={"section": "feed"}
    )
    assert feed.status_code == 200
    actions = [entry["action"] for entry in feed.json()["feed"]]
    assert "run.created" in actions

    bad = await client.get(
        f"/api/team/runs/{run['run_id']}/state", headers=auth, params={"section": "nope"}
    )
    assert bad.status_code == 422  # the section enum is the HTTP gate


# ── the gates are reachable through the routes ───────────────────────────────


async def test_advance_is_refused_by_the_gate_and_then_succeeds(
    run_env: tuple[httpx.AsyncClient, dict[str, str], str, Any],
) -> None:
    client, auth, team_id, bound_service = run_env
    run = await _create_run(client, auth, team_id)

    # No SPEC.md ⇒ the artifact gate refuses, with the plan's code (not a 500).
    refused = await client.post(
        f"/api/team/runs/{run['run_id']}:advance", headers=auth, json={"to_phase": "implement"}
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "TEAM_SPEC_BOUNDARY_EMPTY"

    # The skeleton lands, then the same call goes through.
    bound_service.write_artifact(
        run["run_id"], name="SPEC.md", content=FILLED_SPEC, revision="", role="pm"
    )
    moved = await client.post(
        f"/api/team/runs/{run['run_id']}:advance", headers=auth, json={"to_phase": "implement"}
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["phase"] == "implement"

    skipped = await client.post(
        f"/api/team/runs/{run['run_id']}:advance", headers=auth, json={"to_phase": "deliver"}
    )
    assert skipped.status_code == 409
    assert skipped.json()["error"]["code"] == "TEAM_RUN_PHASE_INVALID"


async def test_task_board_and_the_patch_ops(
    run_env: tuple[httpx.AsyncClient, dict[str, str], str, Any],
) -> None:
    client, auth, team_id, _service = run_env
    run = await _create_run(client, auth, team_id)

    created = await client.post(
        f"/api/team/runs/{run['run_id']}/tasks",
        headers=auth,
        json={
            "title": "写测试",
            "kind": "verification",
            "owner": "qa",
            "acceptance": ["覆盖 G5"],
            "inScope": ["tests/**"],
            "verify": ["uv run pytest -q"],
            "dependsOn": [],
        },
    )
    assert created.status_code == 201, created.text
    task = created.json()
    assert task["inScope"] == ["tests/**"] and task["verify"] == ["uv run pytest -q"]

    board = await client.get(f"/api/team/runs/{run['run_id']}/tasks", headers=auth)
    assert board.status_code == 200
    assert [node["id"] for node in board.json()["nodes"]] == [task["id"]]
    assert board.json()["edges"] == []

    claimed = await client.patch(
        f"/api/team/runs/{run['run_id']}/tasks/{task['id']}",
        headers=auth,
        json={"op": "claim", "attemptId": "", "role": "qa"},
    )
    assert claimed.status_code == 200, claimed.text
    attempt = claimed.json()["attemptId"]
    assert attempt and claimed.json()["attempt"] == 1

    # A stale token is refused (G8) — through the route, with the plan's code.
    stale = await client.patch(
        f"/api/team/runs/{run['run_id']}/tasks/{task['id']}",
        headers=auth,
        json={"op": "report", "attemptId": "att-from-another-round"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "TEAM_ATTEMPT_STALE"

    # Out-of-scope completion is refused; in-scope completion lands.
    violation = await client.patch(
        f"/api/team/runs/{run['run_id']}/tasks/{task['id']}",
        headers=auth,
        json={"op": "complete", "attemptId": attempt, "role": "qa", "changedPaths": ["src/x.py"]},
    )
    assert violation.status_code == 409
    assert violation.json()["error"]["code"] == "TEAM_SCOPE_VIOLATION"

    done = await client.patch(
        f"/api/team/runs/{run['run_id']}/tasks/{task['id']}",
        headers=auth,
        json={"op": "complete", "attemptId": attempt, "role": "qa", "changedPaths": ["tests/x.py"]},
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "review"

    # The op enum is the HTTP gate for unknown verbs.
    unknown = await client.patch(
        f"/api/team/runs/{run['run_id']}/tasks/{task['id']}",
        headers=auth,
        json={"op": "explode", "attemptId": attempt},
    )
    assert unknown.status_code == 422


async def test_artifact_routes_carry_the_revision_cas(
    run_env: tuple[httpx.AsyncClient, dict[str, str], str, Any],
) -> None:
    client, auth, team_id, bound_service = run_env
    run = await _create_run(client, auth, team_id)

    listing = await client.get(f"/api/team/runs/{run['run_id']}/artifacts", headers=auth)
    assert listing.status_code == 200
    names = {item["name"] for item in listing.json()["items"]}
    assert {"SPEC.md", "STATE.json"} <= names  # ownership table ∪ present files

    first = await client.put(
        f"/api/team/runs/{run['run_id']}/artifacts/SPEC.md",
        headers=auth,
        json={"content": "# v1", "revision": "", "role": "pm"},
    )
    assert first.status_code == 200, first.text
    revision = first.json()["revision"]

    denied = await client.put(
        f"/api/team/runs/{run['run_id']}/artifacts/SPEC.md",
        headers=auth,
        json={"content": "# hijack", "revision": revision, "role": "backend"},
    )
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "TEAM_ARTIFACT_OWNERSHIP_DENIED"

    stale = await client.put(
        f"/api/team/runs/{run['run_id']}/artifacts/SPEC.md",
        headers=auth,
        json={"content": "# v2", "revision": "deadbeefdeadbeef", "role": "pm"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "TEAM_ARTIFACT_STALE"

    # T-45 read half: the index row written by the PUT is what the listing reports.
    listing_after = await client.get(f"/api/team/runs/{run['run_id']}/artifacts", headers=auth)
    spec = next(item for item in listing_after.json()["items"] if item["name"] == "SPEC.md")
    assert spec["owner_role"] == "pm"
    assert spec["phase"] == run["phase"]
    assert spec["version"] == 1
    assert spec["hash"] == first.json()["hash"]

    read = await client.get(f"/api/team/runs/{run['run_id']}/artifacts/SPEC.md", headers=auth)
    assert read.status_code == 200
    assert read.json() == {"name": "SPEC.md", "content": "# v1", "revision": revision}


async def test_check_and_decision_and_lifecycle_routes(
    run_env: tuple[httpx.AsyncClient, dict[str, str], str, Any],
) -> None:
    client, auth, team_id, _service = run_env
    run = await _create_run(client, auth, team_id)

    check = await client.get(f"/api/team/runs/{run['run_id']}/check", headers=auth)
    assert check.status_code == 200
    # Nothing recorded a verify run yet, so this is reported, never blocked.
    assert "verify_missing" not in check.json()["violations"]

    # No decision is pending ⇒ the idempotence rule answers 409, not 500.
    not_pending = await client.post(
        f"/api/team/runs/{run['run_id']}/decision",
        headers=auth,
        json={"decision_id": "d1", "choice": "go"},
    )
    assert not_pending.status_code == 409
    assert not_pending.json()["error"]["code"] == "TEAM_DECISION_NOT_PENDING"

    assert (
        await client.post(f"/api/team/runs/{run['run_id']}:resume", headers=auth)
    ).status_code == 200
    cancelled = await client.post(f"/api/team/runs/{run['run_id']}:cancel", headers=auth)
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"

    terminal = await client.post(
        f"/api/team/runs/{run['run_id']}:advance", headers=auth, json={"to_phase": "implement"}
    )
    assert terminal.status_code == 409
    assert terminal.json()["error"]["code"] == "TEAM_RUN_TERMINAL"


async def test_create_refuses_a_bad_mode_and_an_empty_goal(
    run_env: tuple[httpx.AsyncClient, dict[str, str], str, Any],
) -> None:
    client, auth, team_id, _service = run_env

    bad_mode = await client.post(
        "/api/team/runs",
        headers=auth,
        json={"team_agent_id": team_id, "goal": "x", "mode": "persistent"},
    )
    assert bad_mode.status_code == 422  # the Pydantic enum is the user-facing gate

    empty_goal = await client.post(
        "/api/team/runs", headers=auth, json={"team_agent_id": team_id, "goal": "   "}
    )
    assert empty_goal.status_code == 400
    assert empty_goal.json()["error"]["code"] == "TEAM_RUN_GOAL_EMPTY"

    unknown_team = await client.post(
        "/api/team/runs", headers=auth, json={"team_agent_id": "ag-nope", "goal": "x"}
    )
    assert unknown_team.status_code == 404
    assert unknown_team.json()["error"]["code"] == "TEAM_NOT_FOUND"


async def test_the_room_opens_on_the_boot_time_binding(
    run_env: tuple[httpx.AsyncClient, dict[str, str], str, Any],
) -> None:
    """T-67 acceptance ②③, on the production objects, in one test.

    ② **Direct evidence**: this fixture is a *booted* server, so the gateway the boot
    bound is the one the routes now resolve -- and `room_thread_id` comes back non-null.
    Before the fix the routes built a fresh, unbound service and this field was `null`.

    ③ **Control**: "unwired means no room" must be unchanged. The instance the routes
    used to get is reproduced deliberately -- a freshly constructed service -- and it
    still opens nothing; only the memoised, boot-bound one does. The first version of
    this test asserted `null` on the *production* instance and failed, which is itself
    the evidence: the boot binding is now visible to HTTP.
    """
    client, auth, team_id, service = run_env

    assert service._gateway is not None, "the boot chain binds a gateway"
    bound = await _create_run(client, auth, team_id)
    assert bound["room_thread_id"], "the bound gateway must open the room thread"

    # The negative half, on a service built the way the routes used to build one.
    from octop.infra.agents.teams.run_service import TeamRunService

    unbound = TeamRunService(services=service._services)
    assert unbound._gateway is None
    assert service._services.team_run_service() is service, "routes resolve the memoised one"
    assert service._services.team_run_service() is not unbound


async def test_every_bind_runtime_handle_is_visible_only_on_the_route_instance(
    run_env: tuple[httpx.AsyncClient, dict[str, str], str, Any],
) -> None:
    """T-67 acceptance ④, **paired**: the same probe against two instances.

    A one-sided assertion ("the handle is bound") would also pass if the handle had a
    default, so each probe is run twice -- on the instance the routes resolve, and on a
    freshly constructed one (exactly what the routes used to get). What the pair shows
    is that **memoisation is what makes the runtime handles visible**, nothing else.

    Measured, not assumed, and the four handles are not alike:
    ``agent_manager`` / ``gateway`` are bound by the boot (``server.py:455``);
    ``workspace_for`` is not bound there at all -- production relies on the documented
    lazy fallback in ``_workspace_accessor()`` -- and ``kb_archiver_factory`` has **no
    production injector anywhere**, so T-45's archival hop does not run in production.
    That last one is a real gap, pinned here so it cannot be mistaken for "wired".
    """
    _client, _auth, _team_id, service = run_env
    from octop.infra.agents.teams.run_service import TeamRunService

    routed = service._services.team_run_service()
    assert routed is service, "the routes resolve the memoised instance"
    fresh = TeamRunService(services=service._services)

    for handle in ("_agent_manager", "_gateway", "_workspace_for", "_kb_archiver_factory"):
        assert getattr(fresh, handle) is None, f"{handle}: a fresh instance starts unwired"
    assert routed._agent_manager is not None, "boot binds the agent manager"
    assert routed._gateway is not None, "boot binds the gateway (hence the room)"
    # Was (T-67 ④, when there was no injector at all -- kept for grep):
    #   assert routed._kb_archiver_factory is None, "no production injector for the archiver"
    # T-71 wired the injector into the boot's single `bind_runtime` call, so the handle
    # the routes resolve is now bound; the unbound instance still reports `None`.
    assert routed._kb_archiver_factory is not None, "the boot injects the archiver factory"
    assert fresh._kb_archiver_factory is None


async def test_g6_refusals_reach_the_client_over_http_as_409(
    run_env: tuple[httpx.AsyncClient, dict[str, str], str, Any],
) -> None:
    """G6's refusals **through the router** — the layer where they used to die.

    Each of these raised `TypeError` while the error was being serialised (the graph
    refusal carries `details["code"]`, which collided with `error_message`'s own
    parameter), so the service-level tests were green and the client got a 500. Also
    asserts the **localised** message, because "409 with the right code" and "a message
    the user can read" are two different contracts.

    `cycle` is absent **on purpose**: the board has no endpoint that rewrites
    `dependsOn`, so a two-node cycle cannot be built through HTTP at all -- attempting
    it always fails earlier as `missing-id`. It stays covered where it is reachable
    (`tests/unit/agents/test_team_pipeline.py`).
    """
    client, auth, team_id, _service = run_env
    run = await _create_run(client, auth, team_id)
    base = f"/api/team/runs/{run['run_id']}/tasks"
    headers = {**auth, "Accept-Language": "zh-CN"}

    async def refute(payload: dict[str, Any], expected: str) -> dict[str, Any]:
        resp = await client.post(base, headers=headers, json=payload)
        assert resp.status_code == 409, (expected, resp.status_code, resp.text)
        body = resp.json()
        assert body["error"]["code"] == "TEAM_TASK_GRAPH_INVALID"
        assert body["error"]["details"]["code"] == expected
        assert body["error"]["message"] and "任务依赖图" in body["error"]["message"]
        return body

    await refute({"title": "ghost", "dependsOn": ["nope"]}, "missing-id")
    await refute({"id": "self-1", "title": "self", "dependsOn": ["self-1"]}, "self-dependency")

    created = await client.post(base, headers=headers, json={"id": "dup-1", "title": "first"})
    assert created.status_code == 201, created.text
    # Round trip over HTTP: the id is the caller's, not a generated one.
    assert created.json()["id"] == "dup-1"
    await refute({"id": "dup-1", "title": "second"}, "duplicate-id")


async def test_metrics_reaches_the_twelve_sections_over_http(
    run_env: tuple[httpx.AsyncClient, dict[str, str], str, Any],
) -> None:
    """T-47's acceptance: the rollup has a **production entry**, and every section
    says whether it is a real value, a proxy, or an explicit empty state.

    The pure-function half is covered by ``tests/unit/agents/test_team_metrics.py``;
    what is proved here is the wiring — that `/metrics` reaches ``rollup`` at all, and
    that an empty section cannot be mistaken for a measured zero.
    """
    client, auth, team_id, _service = run_env
    run = await _create_run(client, auth, team_id)
    await client.post(
        f"/api/team/runs/{run['run_id']}/tasks",
        headers=auth,
        json={"title": "干活", "kind": "work", "owner": "backend"},
    )

    resp = await client.get(f"/api/team/runs/{run['run_id']}/metrics", headers=auth)
    assert resp.status_code == 200, resp.text
    payload = resp.json()

    titles = [section["title"] for section in payload["sections"]]
    assert len(titles) == 12
    assert titles[0] == "总览" and titles[-1] == "token 成本与上下文峰值"

    states = {section["title"]: section["state"] for section in payload["sections"]}
    # Real values: the timeline/task rows exist.
    assert states["阶段覆盖"] == "measured"
    assert states["角色结果（pass=交付 / rework=返工件 / fail=失败）"] == "measured"
    # `B2` 接线后该节有产出方 ⇒ `measured`（`T01`/`T04`，lead 裁定 2026-09-30 02:35 CST）
    assert states["单源化总扫（见一个，扫全部）"] == "measured"
    # Proxies and explicit empty states (PLAN AM-26) — never silently omitted.
    assert states["首产物（首个可运行产物耗时）"] == "proxy"
    assert states["收尾预算（实现期 = 首产物→冻结 · 收尾 = 冻结→交付）"] == "proxy"
    # Section 10 left this set once `scan:*` got a writer; these two are still
    # genuinely producer-less, so they remain the `empty` positives of the family.
    assert states["高频卡点（error / 返工，去重）"] == "empty"
    assert states["用户高频提问（ask，去重）"] == "empty"
    assert states["评审效率（轮次 / 撤销率）"] == "partial"
    # ...and section 10 keeps its original point on the *body*: with no `scan:*` event
    # yet, the section must still be shown and say the empty case verbatim — an
    # explicit line, never a silent omission and never a fabricated 0.
    scan_index = titles.index("单源化总扫（见一个，扫全部）")
    scan_lines = payload["sections"][scan_index]["lines"]
    assert any("暂无 scan:single-source 事件族" in line for line in scan_lines)
    # No usage row ⇒ the token section must say so, not print 0.
    token_lines = next(
        s["lines"] for s in payload["sections"] if s["title"] == "token 成本与上下文峰值"
    )
    assert any("暂无 token 口径" in line for line in token_lines)

    # The unmetered channel is *stated*, never left as an invisible gap.
    token_note = next(
        s["note"] for s in payload["sections"] if s["title"] == "token 成本与上下文峰值"
    )
    assert "room" in token_note or "房间线程" in token_note
    assert "one-shot" in token_note

    # Idempotent: the same rows render byte-identically.
    again = await client.get(f"/api/team/runs/{run['run_id']}/metrics", headers=auth)
    assert again.json()["rendered"] == payload["rendered"]

    unknown = await client.get("/api/team/runs/nope/metrics", headers=auth)
    assert unknown.status_code == 404


async def test_export_returns_the_requested_projection(
    run_env: tuple[httpx.AsyncClient, dict[str, str], str, Any],
) -> None:
    """T-14's projector gets its consumer: the route renders and returns a projection."""
    client, auth, team_id, _service = run_env
    run = await _create_run(client, auth, team_id)

    resp = await client.get(f"/api/team/runs/{run['run_id']}/export/TASKS.json", headers=auth)
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["name"] == "TASKS.json"
    # The projection is a JSON document keyed by `tasks` (the renderer's current
    # shape). The `"authority": "db"` marker the plan's T-14 row also asks for is
    # **not** emitted by `teams/export.py` yet — reported to the lead as a T-14 gap
    # rather than asserted into this card's test.
    assert '"tasks"' in payload["content"]
    # All four projections are refreshed by one export pass.
    assert sorted(payload["files"]) == ["ROSTER.json", "STATE.json", "TASKS.json", "任务看板.md"]

    # Re-exporting the same state is byte-identical (the projector is idempotent).
    again = await client.get(f"/api/team/runs/{run['run_id']}/export/TASKS.json", headers=auth)
    assert again.json()["content"] == payload["content"]

    unknown = await client.get(f"/api/team/runs/{run['run_id']}/export/NOPE", headers=auth)
    assert unknown.status_code == 422  # the projection name is the HTTP gate


async def test_one_shot_dispatch_reports_its_channel(
    run_env: tuple[httpx.AsyncClient, dict[str, str], str, Any],
) -> None:
    """One-shot starts no room turn — the channel is reported so it cannot be confused."""
    client, auth, team_id, _service = run_env
    run = await _create_run(client, auth, team_id, mode="one-shot")
    task = (
        await client.post(
            f"/api/team/runs/{run['run_id']}/tasks",
            headers=auth,
            json={"title": "子代理活", "kind": "work", "owner": "backend"},
        )
    ).json()

    resp = await client.post(
        f"/api/team/runs/{run['run_id']}/tasks/{task['id']}:dispatch",
        headers=auth,
        json={"op": "claim", "attemptId": "", "role": "backend"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"task_id": task["id"], "channel": "task", "thread_id": None}
