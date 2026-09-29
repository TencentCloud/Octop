"""HTTP contract for the namespace-scoped memory read surface (plan T-37).

Covers the two routes that make the memory "scope" layer visible:

* ``GET /api/agents/{agent_id}/memory/scopes`` — the agent's memory grouped by
  ``agent_{id}`` / ``team_{id}`` / ``project_{id}``, every row tagged with the
  layer it came from.
* ``GET /api/projects/{project_id}/memory`` — the same aggregation behind
  project membership (``PROJECT_READ``), which is the data source for the
  project-memory tab.

Rows are seeded into the real ``octop_memory`` stores over the agent's real
SQLite backend (no LLM, no harness turn). Every "reported once" assertion is
paired with a positive control read of both namespaces, so a silently empty
store cannot make the dedup test pass for the wrong reason.
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
TEAM_ID = "T1"


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def api(
    tmp_octop_home: Path,
) -> AsyncIterator[tuple[httpx.AsyncClient, Any, dict[str, str], str]]:
    """Admin client + server + the bootstrap ``main`` agent id."""
    # The OpenAPI contract test needs the spec endpoint, which is opt-in.
    write_octop_config(tmp_octop_home, enable_api_docs=True)
    async with octop_client(tmp_octop_home) as (client, srv):
        await bootstrap_admin(client, tmp_octop_home)
        admin = await auth_header(client)
        agents = (await client.get("/api/agents", headers=admin)).json()
        assert agents, "bootstrap should have created the main agent"
        yield client, srv, admin, str(agents[0]["agent_id"])


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------


def _memory_for(srv: Any, agent_id: str, namespace: str) -> Any:
    """Open the real store for one namespace, exactly the way production does."""
    from octop_memory.core import Memory

    from octop.infra.agents.memory.backend import open_memory_kwargs

    workspace = srv.app_runtime.agent_registry.resolve_workspace_dir(agent_id)
    row = srv.services.agent_repo.get(agent_id)
    cfg: dict[str, Any] = {}
    if row is not None and row.config_json:
        try:
            parsed = json.loads(row.config_json)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            cfg = parsed

    ns, backend, backend_config = open_memory_kwargs(
        agent_id=agent_id,
        cfg=cfg,
        octop_config=srv.services.config,
        workspace_dir=workspace,
        namespace=namespace,
    )
    return Memory(namespace=ns, backend=backend, backend_config=backend_config)


def _seed(srv: Any, agent_id: str, namespace: str, texts: list[str]) -> None:
    """Write one atom per text into ``namespace`` and close the handle."""
    from octop_memory.types import AtomCard

    memory = _memory_for(srv, agent_id, namespace)
    try:
        for index, text in enumerate(texts):
            memory.add_atom(
                AtomCard(
                    id=f"atom-{namespace}-{index}-{abs(hash(text)) % 10**6}",
                    entity_id=f"ent-{namespace}-{index}",
                    candidate_id=f"cand-{namespace}-{index}",
                    raw_event_ids=[],
                    assertion=text,
                    verbatim_quote=text,
                    quote_event_id="",
                    search_terms=[text],
                    occurred_at=_now(),
                    confidence="high",
                    importance="high",
                    created_at=_now(),
                )
            )
    finally:
        memory.backend.close()


def _stored(srv: Any, agent_id: str, namespace: str, needle: str) -> bool:
    """Positive control: the text really is in that namespace's store."""
    memory = _memory_for(srv, agent_id, namespace)
    try:
        return any(needle in atom.assertion for atom in memory.list_atoms(limit=200))
    finally:
        memory.backend.close()


# ---------------------------------------------------------------------------
# Project / membership helpers
# ---------------------------------------------------------------------------


async def _project(client: httpx.AsyncClient, auth: dict[str, str], name: str) -> str:
    response = await client.post(PROJECTS, headers=auth, json={"name": name, "status": "active"})
    assert response.status_code == 201, response.text
    return str(response.json()["project_id"])


async def _add_member(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    project_id: str,
    user_id: int,
    role: str,
) -> None:
    response = await client.post(
        f"{PROJECTS}/{project_id}/members",
        headers=admin,
        json={"subject_type": "user", "subject_id": str(user_id), "role": role},
    )
    assert response.status_code == 201, response.text


def _groups(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {group["source_layer"]: group for group in body["groups"]}


# ---------------------------------------------------------------------------
# Agent-scoped aggregation: grouping + source_layer
# ---------------------------------------------------------------------------


async def test_scopes_group_by_namespace(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    """T-37 acc.1 — the three namespaces come back as three named groups."""
    client, srv, admin, aid = api
    pid = await _project(client, admin, "scope-grouping")
    _seed(srv, aid, f"agent_{aid}", ["agent-private-fact"])
    _seed(srv, aid, f"team_{TEAM_ID}", ["team-shared-fact"])
    _seed(srv, aid, f"project_{pid}", ["project-owned-fact"])

    response = await client.get(
        f"/api/agents/{aid}/memory/scopes",
        headers=admin,
        params={"project_id": pid, "team_id": TEAM_ID},
    )
    assert response.status_code == 200, response.text
    groups = _groups(response.json())

    assert set(groups) == {"project", "team", "agent"}
    assert groups["agent"]["namespace"] == f"agent_{aid}"
    assert groups["team"]["namespace"] == f"team_{TEAM_ID}"
    assert groups["project"]["namespace"] == f"project_{pid}"
    assert [item["text"] for item in groups["project"]["items"]] == ["project-owned-fact"]
    assert groups["project"]["total"] == 1
    assert groups["project"]["items"][0]["project_id"] == pid


async def test_every_item_carries_its_source_layer(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    """T-37 acc.2 — each row states its layer and namespace, matching its group."""
    client, srv, admin, aid = api
    pid = await _project(client, admin, "scope-labelling")
    _seed(srv, aid, f"agent_{aid}", ["labelled-agent"])
    _seed(srv, aid, f"team_{TEAM_ID}", ["labelled-team"])
    _seed(srv, aid, f"project_{pid}", ["labelled-project"])

    response = await client.get(
        f"/api/agents/{aid}/memory/scopes",
        headers=admin,
        params={"project_id": pid, "team_id": TEAM_ID},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    seen_layers = set()
    for group in body["groups"]:
        assert group["items"], f"group {group['source_layer']} should not be empty here"
        for item in group["items"]:
            assert item["source_layer"] == group["source_layer"]
            assert item["namespace"] == group["namespace"]
            assert item["id"]
            assert item["created_at"]
            seen_layers.add(item["source_layer"])
    assert seen_layers == {"project", "team", "agent"}


async def test_duplicate_across_two_namespaces_is_reported_once(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    """Plan R17 — one fact in two namespaces must not be reported twice.

    The two namespaces are separate stores, so the copies carry different atom
    ids: only the normalized content can identify them as the same memory.
    """
    client, srv, admin, aid = api
    pid = await _project(client, admin, "scope-dedup")
    shared = "shared-fact-between-project-and-agent"
    _seed(srv, aid, f"agent_{aid}", [shared])
    _seed(srv, aid, f"project_{pid}", [shared])

    # Positive control: both stores really hold it.
    assert _stored(srv, aid, f"agent_{aid}", shared)
    assert _stored(srv, aid, f"project_{pid}", shared)

    response = await client.get(
        f"/api/agents/{aid}/memory/scopes",
        headers=admin,
        params={"project_id": pid},
    )
    assert response.status_code == 200, response.text
    groups = _groups(response.json())

    hits = [
        (layer, item)
        for layer, group in groups.items()
        for item in group["items"]
        if item["text"] == shared
    ]
    assert len(hits) == 1, hits
    # The higher layer wins, so the row is filed under the project.
    assert hits[0][0] == "project"


async def test_without_project_context_there_is_no_project_group(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    """Plan B36 / SPEC A5.8③ — no project context ⇒ no project node at all."""
    client, srv, admin, aid = api
    pid = await _project(client, admin, "scope-no-context")
    _seed(srv, aid, f"project_{pid}", ["project-only-fact"])
    _seed(srv, aid, f"agent_{aid}", ["agent-local-fact"])

    response = await client.get(
        f"/api/agents/{aid}/memory/scopes", headers=admin, params={"team_id": TEAM_ID}
    )
    assert response.status_code == 200, response.text
    groups = _groups(response.json())

    assert "project" not in groups
    assert set(groups) == {"team", "agent"}
    assert [item["text"] for item in groups["agent"]["items"]] == ["agent-local-fact"]


async def test_agent_without_a_team_has_no_team_group(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    client, srv, admin, aid = api
    _seed(srv, aid, f"agent_{aid}", ["solo-fact"])

    response = await client.get(f"/api/agents/{aid}/memory/scopes", headers=admin)
    assert response.status_code == 200, response.text
    groups = _groups(response.json())

    assert set(groups) == {"agent"}


async def test_empty_project_is_an_empty_state_not_an_error(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    """A project with no memory yet is a normal starting point (PG: all tables 0)."""
    client, _srv, admin, aid = api
    pid = await _project(client, admin, "scope-empty")

    response = await client.get(
        f"/api/agents/{aid}/memory/scopes", headers=admin, params={"project_id": pid}
    )
    assert response.status_code == 200, response.text
    groups = _groups(response.json())

    assert groups["project"]["total"] == 0
    assert groups["project"]["items"] == []


async def test_non_owner_cannot_read_agent_scopes(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    """T-37 acc.3 — the existing agent-owner guard still applies."""
    client, _srv, admin, aid = api
    alice = await create_user(client, admin, username="scopes-alice")

    response = await client.get(f"/api/agents/{aid}/memory/scopes", headers=alice)
    assert response.status_code == 403, response.text


# ---------------------------------------------------------------------------
# Project-scoped aggregation: membership is the only key
# ---------------------------------------------------------------------------


async def test_project_memory_returns_project_layer_rows(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    """PLAN API面③ — the project tab's shape, project layer only by default."""
    client, srv, admin, aid = api
    pid = await _project(client, admin, "proj-memory-basic")
    _seed(srv, aid, f"project_{pid}", ["project-memory-row"])
    _seed(srv, aid, f"agent_{aid}", ["agent-private-row"])

    response = await client.get(f"{PROJECTS}/{pid}/memory", headers=admin, params={"agent_id": aid})
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["project_id"] == pid
    assert body["next_cursor"] is None
    texts = [item["text"] for item in body["items"]]
    assert texts == ["project-memory-row"]
    item = body["items"][0]
    assert set(item) >= {"id", "text", "source_layer", "created_at"}
    assert item["source_layer"] == "project"


async def test_project_memory_all_scope_includes_every_layer(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    client, srv, admin, aid = api
    pid = await _project(client, admin, "proj-memory-all")
    _seed(srv, aid, f"project_{pid}", ["all-project-row"])
    _seed(srv, aid, f"team_{TEAM_ID}", ["all-team-row"])

    response = await client.get(
        f"{PROJECTS}/{pid}/memory",
        headers=admin,
        params={"agent_id": aid, "scope": "all", "team_id": TEAM_ID},
    )
    assert response.status_code == 200, response.text
    layers = {item["source_layer"] for item in response.json()["items"]}

    assert layers == {"project", "team"}


async def test_project_memory_paginates_with_an_opaque_cursor(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    client, srv, admin, aid = api
    pid = await _project(client, admin, "proj-memory-page")
    _seed(srv, aid, f"project_{pid}", ["page-row-one", "page-row-two"])

    first = await client.get(
        f"{PROJECTS}/{pid}/memory", headers=admin, params={"agent_id": aid, "limit": 1}
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert len(body["items"]) == 1
    assert body["next_cursor"] is not None

    second = await client.get(
        f"{PROJECTS}/{pid}/memory",
        headers=admin,
        params={"agent_id": aid, "limit": 1, "cursor": body["next_cursor"]},
    )
    assert second.status_code == 200, second.text
    assert len(second.json()["items"]) == 1
    assert second.json()["next_cursor"] is None

    bad = await client.get(
        f"{PROJECTS}/{pid}/memory",
        headers=admin,
        params={"agent_id": aid, "cursor": "not-a-number"},
    )
    assert bad.status_code == 400, bad.text


async def test_project_memory_empty_state_is_not_an_error(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    client, _srv, admin, aid = api
    pid = await _project(client, admin, "proj-memory-empty")

    response = await client.get(f"{PROJECTS}/{pid}/memory", headers=admin, params={"agent_id": aid})
    assert response.status_code == 200, response.text
    assert response.json()["items"] == []


async def test_project_memory_requires_membership(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    """SPEC §11.3 — non-members get 403 PROJECT_FORBIDDEN, and no rows."""
    client, _srv, admin, aid = api
    pid = await _project(client, admin, "proj-memory-forbidden")
    bob = await create_user(client, admin, username="scopes-bob")

    response = await client.get(f"{PROJECTS}/{pid}/memory", headers=bob, params={"agent_id": aid})
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "PROJECT_FORBIDDEN"


async def test_admin_who_is_not_a_member_is_also_rejected(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    """SPEC §11.3 — the admin flag does not bypass project membership."""
    client, _srv, admin, aid = api
    pid = await _project(client, admin, "proj-memory-admin")
    second_admin = await create_user(client, admin, username="scopes-admin2", role="admin")

    response = await client.get(
        f"{PROJECTS}/{pid}/memory", headers=second_admin, params={"agent_id": aid}
    )
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "PROJECT_FORBIDDEN"


async def test_viewer_role_can_read_project_memory(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    """SPEC §11.4 — a viewer may read project memory (write is a separate action)."""
    client, srv, admin, aid = api
    pid = await _project(client, admin, "proj-memory-viewer")
    _seed(srv, aid, f"project_{pid}", ["viewer-readable-row"])

    viewer = await create_user(client, admin, username="scopes-viewer")
    viewer_id = await resolve_user_id(client, admin, "scopes-viewer")
    await _add_member(client, admin, pid, viewer_id, "viewer")

    response = await client.get(
        f"{PROJECTS}/{pid}/memory", headers=viewer, params={"agent_id": aid}
    )
    assert response.status_code == 200, response.text
    assert [item["text"] for item in response.json()["items"]] == ["viewer-readable-row"]


async def test_unknown_project_is_404(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    client, _srv, admin, aid = api
    response = await client.get(
        f"{PROJECTS}/NO-SUCH-PROJECT/memory", headers=admin, params={"agent_id": aid}
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "PROJECT_NOT_FOUND"


# ---------------------------------------------------------------------------
# Reading the project layer is gated by membership on EVERY path (SPEC §11.3/B38)
#
# A defensive audit found the agent-scoped route could reach ``project_{id}``
# with only agent-ownership checked. These tests pin the gate on both routes so
# "invisible" and "forbidden" can never be confused again.
# ---------------------------------------------------------------------------


async def _member_agent(
    client: httpx.AsyncClient, admin: dict[str, str], username: str
) -> tuple[dict[str, str], str]:
    """A user with their own agent (so the agent-owner check passes)."""
    auth = await create_user(client, admin, username=username)
    agent_id = await create_agent(client, auth, name=f"{username}-agent")
    return auth, agent_id


def _set_memory_namespace(srv: Any, project_id: str, value: str) -> None:
    """Force a distinctive ``projects.memory_namespace`` (the custom-ns case)."""
    with srv.services.db.transaction() as conn:
        conn.execute(
            "UPDATE projects SET memory_namespace = ? WHERE project_id = ?",
            (value, project_id),
        )


async def test_agent_route_rejects_a_non_member_with_project_context(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    """Acc.1 — agent ownership is not enough to read a project's layer."""
    client, srv, admin, _aid = api
    pid = await _project(client, admin, "gate-nonmember")
    alice, alice_agent = await _member_agent(client, admin, "gate-alice")

    # The data really is in alice's own backend; the 403 must come from the
    # gate, not from an empty store.
    _seed(srv, alice_agent, f"project_{pid}", ["gated-project-fact"])
    assert _stored(srv, alice_agent, f"project_{pid}", "gated-project-fact")

    response = await client.get(
        f"/api/agents/{alice_agent}/memory/scopes", headers=alice, params={"project_id": pid}
    )
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "PROJECT_FORBIDDEN"
    assert "gated-project-fact" not in response.text


async def test_agent_route_still_serves_a_project_member(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    """Acc.2 (positive control) — the gate is membership, not a blanket denial.

    A ``viewer`` sees the project layer through the agent-scoped route, so the
    403 above can only be explained by the missing membership.
    """
    client, srv, admin, _aid = api
    pid = await _project(client, admin, "gate-member")
    viewer, viewer_agent = await _member_agent(client, admin, "gate-viewer")
    viewer_id = await resolve_user_id(client, admin, "gate-viewer")
    await _add_member(client, admin, pid, viewer_id, "viewer")
    _seed(srv, viewer_agent, f"project_{pid}", ["member-visible-fact"])

    response = await client.get(
        f"/api/agents/{viewer_agent}/memory/scopes",
        headers=viewer,
        params={"project_id": pid},
    )
    assert response.status_code == 200, response.text
    groups = _groups(response.json())
    assert [item["text"] for item in groups["project"]["items"]] == ["member-visible-fact"]


async def test_non_member_never_learns_the_project_namespace(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    """Acc.5 — the project's ``memory_namespace`` must not leak to a non-member.

    Differential: a member's response *does* carry the custom namespace, so the
    non-member assertion is about the gate and not about a namespace that never
    appears anywhere.
    """
    client, srv, admin, _aid = api
    pid = await _project(client, admin, "gate-ns")
    sentinel_ns = f"CUSTOM-NS-SENTINEL-{pid}"
    _set_memory_namespace(srv, pid, sentinel_ns)

    viewer, viewer_agent = await _member_agent(client, admin, "gate-ns-viewer")
    viewer_id = await resolve_user_id(client, admin, "gate-ns-viewer")
    await _add_member(client, admin, pid, viewer_id, "viewer")
    _seed(srv, viewer_agent, sentinel_ns, ["custom-ns-fact"])

    member = await client.get(
        f"/api/agents/{viewer_agent}/memory/scopes",
        headers=viewer,
        params={"project_id": pid},
    )
    assert member.status_code == 200, member.text
    assert sentinel_ns in member.text  # the namespace is real and renderable
    assert _groups(member.json())["project"]["namespace"] == sentinel_ns

    outsider, outsider_agent = await _member_agent(client, admin, "gate-ns-outsider")
    blocked = await client.get(
        f"/api/agents/{outsider_agent}/memory/scopes",
        headers=outsider,
        params={"project_id": pid},
    )
    assert blocked.status_code == 403, blocked.text
    assert sentinel_ns not in blocked.text


async def test_agent_route_without_project_id_is_unchanged(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    """Acc.3 — no project context means no project gate and no project group."""
    client, srv, admin, _aid = api
    pid = await _project(client, admin, "gate-zero-regression")
    del pid
    alice, alice_agent = await _member_agent(client, admin, "gate-plain")
    _seed(srv, alice_agent, f"agent_{alice_agent}", ["plain-agent-fact"])

    response = await client.get(f"/api/agents/{alice_agent}/memory/scopes", headers=alice)
    assert response.status_code == 200, response.text
    groups = _groups(response.json())
    assert set(groups) == {"agent"}
    assert [item["text"] for item in groups["agent"]["items"]] == ["plain-agent-fact"]


# ---------------------------------------------------------------------------
# OpenAPI contract (both new routes stay documented and correctly tagged)
# ---------------------------------------------------------------------------


async def test_new_routes_are_documented_and_tagged(
    api: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    """A route that renders as an empty card in /api/docs is unfinished.

    The project-scoped route also has to carry the ``projects`` tag: the projects
    OpenAPI contract test asserts every ``/api/projects*`` route does.
    """
    client, _srv, _admin, _aid = api
    spec = (await client.get("/api/openapi.json")).json()

    agent_path = "/api/agents/{agent_id}/memory/scopes"
    project_path = "/api/projects/{project_id}/memory"
    assert agent_path in spec["paths"]
    assert project_path in spec["paths"]

    agent_op = spec["paths"][agent_path]["get"]
    assert agent_op["summary"].strip()
    assert "memory" in agent_op["tags"]
    assert "200" in agent_op["responses"]

    project_op = spec["paths"][project_path]["get"]
    assert project_op["summary"].strip()
    assert "projects" in project_op["tags"]
    assert "200" in project_op["responses"]
