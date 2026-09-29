"""HTTP contract for the project-directed memory **write** surface (plan T-50).

PLAN 「写入路径」 rows 2 and 4 finally have a server side:

* ``POST /api/agents/{aid}/memory/candidates/{cid}:promote`` — with an optional
  ``{"project_id": …}`` body the candidate is adopted into ``project_{pid}``;
  **without** it the call is the pre-existing agent-private adoption, byte for
  byte (the two-argument client shape is load-bearing for the dashboard test).
* ``POST /api/agents/{aid}/memory/atoms/{atom_id}:record-to-project`` — the
  explicit 「记到项目」 action.

Permissions follow SPEC ``B38``: reading is gated by ``project_members``
(``viewer`` included), writing by the project's **write** action — the two are
never merged, so ``viewer`` reads the same project it cannot write to. Every
"written into the project layer" assertion is read back **over HTTP** through the
existing T-37 read route, and every refusal is paired with a success.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from tests.support.app import octop_client, write_octop_config
from tests.support.auth import (
    auth_header,
    bootstrap_admin,
    create_agent,
    create_user,
    resolve_user_id,
)

PROJECTS = "/api/projects"


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def api(
    tmp_octop_home: Path,
) -> AsyncIterator[tuple[httpx.AsyncClient, Any, dict[str, str], str]]:
    write_octop_config(tmp_octop_home, enable_api_docs=True)
    async with octop_client(tmp_octop_home) as (client, srv):
        await bootstrap_admin(client, tmp_octop_home)
        admin = await auth_header(client)
        agents = (await client.get("/api/agents", headers=admin)).json()
        assert agents, "bootstrap should have created the main agent"
        yield client, srv, admin, str(agents[0]["agent_id"])


# ---------------------------------------------------------------------------
# Seeding / reading helpers (real stores, the way production opens them)
# ---------------------------------------------------------------------------


def _agent_cfg(srv: Any, agent_id: str) -> dict[str, Any]:
    """The agent's parsed ``config_json`` (where its memory backend is configured)."""
    row = srv.services.agent_repo.get(agent_id)
    if row is not None and row.config_json:
        try:
            parsed = json.loads(row.config_json)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
    return {}


def _agent_backend_path(srv: Any, agent_id: str) -> Any:
    """Where this agent's memory store really lives — from the source of truth."""
    from octop.api.common.agent_workspace import resolve_agent_workspace_dir
    from octop.api.common.memory_client import memory_db_path_for_cfg

    return memory_db_path_for_cfg(
        resolve_agent_workspace_dir(srv, agent_id), _agent_cfg(srv, agent_id)
    )


def _memory_for(srv: Any, agent_id: str, namespace: str) -> Any:
    from octop_memory.core import Memory

    from octop.api.common.agent_workspace import resolve_agent_workspace_dir
    from octop.infra.agents.memory.backend import open_memory_kwargs

    ns, backend, backend_config = open_memory_kwargs(
        agent_id=agent_id,
        cfg=_agent_cfg(srv, agent_id),
        octop_config=srv.services.config,
        workspace_dir=resolve_agent_workspace_dir(srv, agent_id),
        namespace=namespace,
    )
    return Memory(namespace=ns, backend=backend, backend_config=backend_config)


def _seed_candidate(srv: Any, agent_id: str, candidate_id: str, assertion: str) -> None:
    from octop_memory.types import Candidate

    memory = _memory_for(srv, agent_id, f"agent_{agent_id}")
    try:
        memory.add_candidate(
            Candidate(
                id=candidate_id,
                raw_event_ids=[],
                candidate_type="Preference",
                status="needs_review",
                title=assertion,
                assertion=assertion,
                verbatim_quote=assertion,
                quote_event_id="",
                subject_name="user",
                subject_entity_type="User",
                target_entity_id="ent-1",
                confidence="high",
                importance="high",
                recommended_action="promote",
                promotion_reason="seed",
                extractor_version="test",
                created_at=_now(),
            )
        )
    finally:
        memory.backend.close()


def _seed_atom(srv: Any, agent_id: str, atom_id: str, assertion: str) -> None:
    from octop_memory.types import AtomCard

    memory = _memory_for(srv, agent_id, f"agent_{agent_id}")
    try:
        memory.add_atom(
            AtomCard(
                id=atom_id,
                entity_id="ent-1",
                candidate_id="cand-seed",
                raw_event_ids=[],
                assertion=assertion,
                verbatim_quote=assertion,
                quote_event_id="",
                search_terms=["seed"],
                occurred_at=_now(),
                confidence="high",
                importance="high",
                created_at=_now(),
            )
        )
    finally:
        memory.backend.close()


def _assertions(srv: Any, agent_id: str, namespace: str) -> list[str]:
    memory = _memory_for(srv, agent_id, namespace)
    try:
        return [atom.assertion for atom in memory.list_atoms(limit=200)]
    finally:
        memory.backend.close()


async def _project(client: httpx.AsyncClient, auth: dict[str, str], name: str) -> str:
    response = await client.post(PROJECTS, headers=auth, json={"name": name, "status": "active"})
    assert response.status_code == 201, response.text
    return str(response.json()["project_id"])


async def _add_member(
    client: httpx.AsyncClient, admin: dict[str, str], project_id: str, user_id: int, role: str
) -> None:
    response = await client.post(
        f"{PROJECTS}/{project_id}/members",
        headers=admin,
        json={"subject_type": "user", "subject_id": str(user_id), "role": role},
    )
    assert response.status_code == 201, response.text


async def _member_with_own_agent(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    project_id: str,
    username: str,
    role: str | None,
) -> tuple[dict[str, str], str]:
    """A user with their own agent — so the agent-owner gate passes and the
    project gate is what the test actually measures (``role=None`` ⇒ not a member)."""
    headers = await create_user(client, admin, username=username)
    agent_id = await create_agent(client, headers, name=f"{username}-agent")
    if role is not None:
        user_id = await resolve_user_id(client, admin, username)
        await _add_member(client, admin, project_id, user_id, role)
    return headers, agent_id


async def _promote(
    client: httpx.AsyncClient, auth: dict[str, str], agent_id: str, candidate_id: str, **body: Any
) -> httpx.Response:
    kwargs: dict[str, Any] = {} if not body else {"json": body}
    return await client.post(
        f"/api/agents/{agent_id}/memory/candidates/{candidate_id}:promote",
        headers=auth,
        **kwargs,
    )


async def _project_rows(
    client: httpx.AsyncClient, auth: dict[str, str], project_id: str, agent_id: str
) -> httpx.Response:
    return await client.get(
        f"{PROJECTS}/{project_id}/memory",
        headers=auth,
        params={"agent_id": agent_id, "scope": "project"},
    )


# ---------------------------------------------------------------------------
# ① Adoption with a target: written into project_{pid}, readable from it
# ---------------------------------------------------------------------------


async def test_promote_with_project_id_lands_in_the_project_namespace(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    client, srv, admin, aid = api
    pid = await _project(client, admin, "adopt-into-project")
    _seed_candidate(srv, aid, "cand-project", "这条经验归属项目")

    response = await _promote(client, admin, aid, "cand-project", project_id=pid)

    assert response.status_code == 200, response.text
    assert response.json()["promoted"] == 1
    assert response.json()["target_layer"] == "project"

    # Read back over HTTP through the pre-existing project-memory route.
    rows = await _project_rows(client, admin, pid, aid)
    assert rows.status_code == 200, rows.text
    assert [item["text"] for item in rows.json()["items"]] == ["这条经验归属项目"]

    # The private layer is untouched by a project-directed adoption.
    assert _assertions(srv, aid, f"agent_{aid}") == []


async def test_promote_without_a_body_still_lands_in_the_private_layer(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    """Positive control for the default path: the two-argument shape is unchanged."""
    client, srv, admin, aid = api
    pid = await _project(client, admin, "adopt-private")
    _seed_candidate(srv, aid, "cand-private", "这条经验留在私有层")

    response = await _promote(client, admin, aid, "cand-private")

    assert response.status_code == 200, response.text
    assert response.json()["promoted"] == 1
    assert "target_layer" not in response.json(), "默认路径不引入新字段"
    assert _assertions(srv, aid, f"agent_{aid}") == ["这条经验留在私有层"]

    rows = await _project_rows(client, admin, pid, aid)
    assert rows.json()["items"] == [], "默认采纳一个字节都不进项目层"


async def test_unknown_candidate_is_not_found(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    client, _srv, admin, aid = api
    pid = await _project(client, admin, "adopt-missing")

    response = await _promote(client, admin, aid, "cand-nope", project_id=pid)

    assert response.status_code == 404, response.text


# ---------------------------------------------------------------------------
# ② Permissions: read is membership, write is the project's write action
# ---------------------------------------------------------------------------


async def test_viewer_can_read_the_project_but_cannot_write_into_it(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    """SPEC B38 (sec's UI case ④): readable must not imply writable."""
    client, srv, admin, _aid = api
    pid = await _project(client, admin, "write-gate-viewer")
    viewer, viewer_agent = await _member_with_own_agent(client, admin, pid, "t50-viewer", "viewer")
    _seed_candidate(srv, viewer_agent, "cand-viewer", "viewer 读得到但写不进")

    readable = await _project_rows(client, viewer, pid, viewer_agent)
    assert readable.status_code == 200, "viewer 是成员 ⇒ 读放行"

    refused = await _promote(client, viewer, viewer_agent, "cand-viewer", project_id=pid)
    assert refused.status_code == 403, refused.text
    # Both codes are pre-existing: a non-member is refused for membership, a
    # member whose role lacks the action for the role (``viewer`` hits this one).
    assert refused.json()["error"]["code"] in {"PROJECT_FORBIDDEN", "PROJECT_ROLE_FORBIDDEN"}
    assert _assertions(srv, viewer_agent, f"project_{pid}") == [], "被拒 ⇒ 一条都不许写进去"


async def test_member_and_owner_can_write_into_the_project(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    client, srv, admin, owner_agent = api
    pid = await _project(client, admin, "write-gate-member")
    member, member_agent = await _member_with_own_agent(client, admin, pid, "t50-member", "member")
    _seed_candidate(srv, member_agent, "cand-member", "member 写得进")
    _seed_candidate(srv, owner_agent, "cand-owner", "owner 写得进")

    by_member = await _promote(client, member, member_agent, "cand-member", project_id=pid)
    assert by_member.status_code == 200, by_member.text
    by_owner = await _promote(client, admin, owner_agent, "cand-owner", project_id=pid)
    assert by_owner.status_code == 200, by_owner.text

    assert _assertions(srv, member_agent, f"project_{pid}") == ["member 写得进"]
    assert _assertions(srv, owner_agent, f"project_{pid}") == ["owner 写得进"]
    # The member can read back what they wrote, over HTTP.
    rows = await _project_rows(client, member, pid, member_agent)
    assert [item["text"] for item in rows.json()["items"]] == ["member 写得进"]


async def test_non_member_cannot_write_into_the_project(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    client, srv, admin, _aid = api
    pid = await _project(client, admin, "write-gate-outsider")
    outsider, outsider_agent = await _member_with_own_agent(
        client, admin, pid, "t50-outsider", None
    )
    _seed_candidate(srv, outsider_agent, "cand-outside", "非成员写不进")

    response = await _promote(client, outsider, outsider_agent, "cand-outside", project_id=pid)

    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "PROJECT_FORBIDDEN"
    assert _assertions(srv, outsider_agent, f"project_{pid}") == []


async def test_admin_who_is_not_a_member_is_also_refused(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    """Membership guards project data — the platform admin flag is not a bypass."""
    client, srv, admin, aid = api
    pid = await _project(client, admin, "write-gate-admin-bypass")
    _seed_candidate(srv, aid, "cand-admin", "admin 非成员也写不进")
    other_admin = await create_user(client, admin, username="t50-admin", role="admin")

    response = await _promote(client, other_admin, aid, "cand-admin", project_id=pid)

    assert response.status_code == 403, response.text
    assert _assertions(srv, aid, f"project_{pid}") == []


# ---------------------------------------------------------------------------
# 「记到项目」 (PLAN row 4)
# ---------------------------------------------------------------------------


async def test_record_to_project_copies_the_memory_and_is_idempotent(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    client, srv, admin, aid = api
    pid = await _project(client, admin, "record-to-project")
    _seed_atom(srv, aid, "atom-1", "记到项目的这条记忆")

    first = await client.post(
        f"/api/agents/{aid}/memory/atoms/atom-1:record-to-project",
        headers=admin,
        json={"project_id": pid},
    )
    assert first.status_code == 200, first.text
    assert first.json() == {"recorded": True, "atom_id": "atom-1", "target_layer": "project"}

    rows = await _project_rows(client, admin, pid, aid)
    assert [item["text"] for item in rows.json()["items"]] == ["记到项目的这条记忆"]

    second = await client.post(
        f"/api/agents/{aid}/memory/atoms/atom-1:record-to-project",
        headers=admin,
        json={"project_id": pid},
    )
    assert second.status_code == 200, second.text
    assert second.json()["recorded"] is False, "幂等：项目层已有同 id 就不再写"
    assert _assertions(srv, aid, f"project_{pid}") == ["记到项目的这条记忆"]


async def test_record_to_project_requires_the_write_action(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    client, srv, admin, _aid = api
    pid = await _project(client, admin, "record-write-gate")
    viewer, viewer_agent = await _member_with_own_agent(
        client, admin, pid, "t50-record-viewer", "viewer"
    )
    _seed_atom(srv, viewer_agent, "atom-viewer", "viewer 记不进去")

    readable = await _project_rows(client, viewer, pid, viewer_agent)
    assert readable.status_code == 200

    refused = await client.post(
        f"/api/agents/{viewer_agent}/memory/atoms/atom-viewer:record-to-project",
        headers=viewer,
        json={"project_id": pid},
    )
    assert refused.status_code == 403, refused.text
    assert _assertions(srv, viewer_agent, f"project_{pid}") == []


async def test_record_to_project_rejects_an_unknown_atom(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    client, _srv, admin, aid = api
    pid = await _project(client, admin, "record-missing")

    response = await client.post(
        f"/api/agents/{aid}/memory/atoms/atom-nope:record-to-project",
        headers=admin,
        json={"project_id": pid},
    )

    assert response.status_code == 404, response.text


# ---------------------------------------------------------------------------
# ③ Only memory content moves — never a document body (T-39 iron rule)
# ---------------------------------------------------------------------------


async def test_project_layer_receives_the_memory_content_not_a_document_body(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    client, srv, admin, aid = api
    pid = await _project(client, admin, "content-not-body")
    _seed_candidate(srv, aid, "cand-content", "记忆内容本身")

    await _promote(client, admin, aid, "cand-content", project_id=pid)

    rows = (await _project_rows(client, admin, pid, aid)).json()["items"]
    assert [row["text"] for row in rows] == ["记忆内容本身"]
    payload = json.dumps(rows, ensure_ascii=False)
    for forbidden in ("kb_document_id", "attachment", "uri", "mime"):
        assert forbidden not in payload, "写入面只搬记忆内容，不搬任何文档字段"


# ---------------------------------------------------------------------------
# Contract: 共享粒度 = agent 的记忆后端（**不是** project_id）
#
# 这条契约是用户决策的输入，所以它是一个断言，不是一段散文：
#
#   * **同一 agent_id + 同一 project_{pid} ⇒ 同一份**（写读一致）；
#   * **跨 agent_id ⇒ 各自一份**（SQLite：每个 agent 一个 ``memory.sqlite``）；
#   * ⇒ 于是"项目记忆在成员之间共享"**只在 PG（共享 schema + namespace 列）下成立**。
#
# ⚠️ **PG 侧未验证**：本机（以及本条用例）跑的是 SQLite，逐 agent 一个文件；
#    PG 的跨成员共享是**推论**（由 `octop_memory` 的 namespace 列语义得出），
#    **不是实测** —— 本仓当前没有可跑的 PG 实例。**不得**把这一条读成"PG 已证"。
# ---------------------------------------------------------------------------


async def test_project_namespace_is_private_to_each_agents_memory_backend(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    """契约断言 + 正对照：同一 OCTOP_HOME 下，两个 agent 的 ``project_{pid}`` 互不可见。"""
    from octop.infra.utils.paths import PathLayout

    client, srv, admin, agent_a = api
    pid = await _project(client, admin, "sharing-granularity")
    # A second agent **of the same user, on the same OCTOP_HOME** — so the only
    # variable left is the memory backend, not the account or the home directory.
    agent_b = await create_agent(client, admin, name="t50-second-agent")

    # Expected values come from the source of truth — no hand-written path literals.
    backend_a = _agent_backend_path(srv, agent_a)
    backend_b = _agent_backend_path(srv, agent_b)
    assert PathLayout.from_env().root in backend_a.parents
    assert PathLayout.from_env().root in backend_b.parents
    assert backend_a != backend_b, "SQLite：两个 agent 的记忆后端就是两个文件"

    # The store this test writes through is exactly the one the source of truth names:
    # ``_memory_for`` resolves through ``open_memory_kwargs``, so pin the two together
    # rather than trusting the helper by construction.
    from octop.api.common.agent_workspace import resolve_agent_workspace_dir
    from octop.infra.agents.memory.backend import open_memory_kwargs

    _ns, _backend, backend_config = open_memory_kwargs(
        agent_id=agent_a,
        cfg=_agent_cfg(srv, agent_a),
        octop_config=srv.services.config,
        workspace_dir=resolve_agent_workspace_dir(srv, agent_a),
        namespace=f"project_{pid}",
    )
    assert backend_config is not None
    assert Path(str(backend_config["db_path"])) == backend_a

    # ── positive control: same agent ⇒ same store ⇒ readable ──
    _seed_candidate(srv, agent_a, "cand-shared", "只应属于 A 的项目层")
    written = await _promote(client, admin, agent_a, "cand-shared", project_id=pid)
    assert written.status_code == 200, written.text
    via_a = await _project_rows(client, admin, pid, agent_a)
    assert [item["text"] for item in via_a.json()["items"]] == ["只应属于 A 的项目层"]

    # ── the assertion: a different agent_id reads its *own* file ⇒ nothing there ──
    via_b = await _project_rows(client, admin, pid, agent_b)
    assert via_b.status_code == 200, via_b.text
    assert via_b.json()["items"] == [], (
        "project_{pid} 不是跨 agent 共享的存储：它落在每个 agent 自己的 memory.sqlite 里。"
        "PG（共享 schema + namespace 列）下才等价于跨成员共享 —— 那一侧本用例未验证。"
    )
    assert _assertions(srv, agent_b, f"project_{pid}") == []
