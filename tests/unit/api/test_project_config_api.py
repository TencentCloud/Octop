"""Real-HTTP end-to-end for the second-batch project config surface (T-INT2).

Exercises the four newly mounted routers through the real app: connector
declarations, project cron jobs, the project instruction, and the skill
projection. Each subsystem is asserted on its **status code and response shape**,
including the authorization refusals a non-member gets.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from tests.support.app import octop_client
from tests.support.auth import auth_header, bootstrap_admin, create_user

PROJECTS = "/api/projects"
AGENT_ID = "ag-exec"


@pytest.fixture
async def api(tmp_octop_home: Path) -> AsyncIterator[tuple[httpx.AsyncClient, Any, dict[str, Any]]]:
    async with octop_client(tmp_octop_home) as (client, srv):
        await bootstrap_admin(client, tmp_octop_home)
        admin = await auth_header(client)
        bob = await create_user(client, admin, username="bob")
        created = await client.post(
            f"{PROJECTS}", headers=admin, json={"name": "Apollo", "status": "active"}
        )
        assert created.status_code == 201, created.text
        pid = created.json()["project_id"]
        srv.services.agent_repo.create(agent_id=AGENT_ID, user_id=1, name="Exec")
        member = await client.post(
            f"{PROJECTS}/{pid}/members",
            headers=admin,
            json={"subject_type": "agent", "subject_id": AGENT_ID, "role": "member"},
        )
        assert member.status_code == 201, member.text
        yield client, srv, {"admin": admin, "bob": bob, "pid": pid}


async def test_connectors_read_replace_and_duplicate(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, _, ctx = api
    pid = ctx["pid"]

    listed = await client.get(f"{PROJECTS}/{pid}/connectors", headers=ctx["admin"])
    assert listed.status_code == 200, listed.text
    assert listed.json() == [], "a project with no declaration answers a bare array"

    replaced = await client.put(
        f"{PROJECTS}/{pid}/connectors", headers=ctx["admin"], json={"kinds": []}
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json() == []

    duplicate = await client.put(
        f"{PROJECTS}/{pid}/connectors",
        headers=ctx["admin"],
        json={"kinds": ["notion", "notion"]},
    )
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.status_code != 500
    assert duplicate.json()["error"]["code"] == "PROJECT_CONNECTOR_INVALID"

    unknown = await client.put(
        f"{PROJECTS}/{pid}/connectors", headers=ctx["admin"], json={"kinds": ["nope"]}
    )
    assert unknown.status_code == 400, unknown.text
    assert unknown.json()["error"]["code"] == "PROJECT_CONNECTOR_INVALID"


async def test_cron_full_cycle_and_delete_envelope(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, _, ctx = api
    pid, auth = ctx["pid"], ctx["admin"]

    assert (await client.get(f"{PROJECTS}/{pid}/cron", headers=auth)).json() == []

    created = await client.post(
        f"{PROJECTS}/{pid}/cron",
        headers=auth,
        json={"agent_id": AGENT_ID, "schedule_spec": "@every 1h", "prompt": "ping"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["owned_by_me"] is True and body["prompt"] == "ping"
    assert body["prompt_hidden"] is False
    cron_id = body["cron_id"]

    listed = await client.get(f"{PROJECTS}/{pid}/cron", headers=auth)
    assert [job["cron_id"] for job in listed.json()] == [cron_id]

    toggled = await client.patch(
        f"{PROJECTS}/{pid}/cron/{cron_id}", headers=auth, json={"enabled": False}
    )
    assert toggled.status_code == 200, toggled.text
    assert toggled.json()["enabled"] is False

    non_member_agent = await client.post(
        f"{PROJECTS}/{pid}/cron",
        headers=auth,
        json={"agent_id": "ag-ghost", "schedule_spec": "@every 1h", "prompt": "x"},
    )
    assert non_member_agent.status_code == 409, non_member_agent.text
    assert non_member_agent.json()["error"]["code"] == "PROJECT_CRON_INVALID"

    deleted = await client.delete(f"{PROJECTS}/{pid}/cron/{cron_id}", headers=auth)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"deleted": True}, "the delete envelope keeps the key name"
    assert (await client.get(f"{PROJECTS}/{pid}/cron", headers=auth)).json() == []


async def test_instruction_round_trip(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, _, ctx = api
    pid, auth = ctx["pid"], ctx["admin"]

    empty = await client.get(f"{PROJECTS}/{pid}/instruction", headers=auth)
    assert empty.status_code == 200, empty.text
    assert empty.json()["instruction"] == "", "an unset instruction is empty, not an error"

    written = await client.put(
        f"{PROJECTS}/{pid}/instruction", headers=auth, json={"instruction": "keep it short"}
    )
    assert written.status_code == 200, written.text
    assert written.json()["instruction"] == "keep it short"
    read_back = await client.get(f"{PROJECTS}/{pid}/instruction", headers=auth)
    assert read_back.json()["instruction"] == "keep it short"


async def test_skills_get_and_put_share_one_shape(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, _, ctx = api
    pid, auth = ctx["pid"], ctx["admin"]

    listed = await client.get(f"{PROJECTS}/{pid}/skills", headers=auth)
    assert listed.status_code == 200, listed.text
    assert set(listed.json()) == {"effective", "stale"}

    replaced = await client.put(f"{PROJECTS}/{pid}/skills", headers=auth, json={"skills": []})
    assert replaced.status_code == 200, replaced.text
    assert set(replaced.json()) == set(listed.json()), "PUT echoes the GET shape"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/connectors"),
        ("GET", "/cron"),
        ("GET", "/instruction"),
        ("GET", "/skills"),
    ],
)
async def test_non_member_is_refused_on_every_new_endpoint(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]], method: str, path: str
) -> None:
    client, _, ctx = api
    response = await client.request(method, f"{PROJECTS}/{ctx['pid']}{path}", headers=ctx["bob"])
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "PROJECT_FORBIDDEN"
