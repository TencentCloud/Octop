"""门二 (PLAN.md §2): reading a knowledge base through a project binding.

Real app + real SQLite + real HTTP: the authorisation chain is exactly the one the
server runs (nothing about the request path is mocked), which is what makes these
re-runnable in CI where the hand-run probes are not.

The rule under test: a base that is **not** owner / shared / admin readable is still
readable by a member of a project bound to it — existing three conditions first,
project membership as the fallback, no "any signed-in user" back door.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from tests.support.app import octop_client
from tests.support.auth import auth_header, bootstrap_admin, create_user, resolve_user_id

KB = "/api/knowledge-bases"
PROJECTS = "/api/projects"
FORBIDDEN = "KNOWLEDGE_FORBIDDEN"
NOT_FOUND = "KNOWLEDGE_NOT_FOUND"


@pytest.fixture
async def env(tmp_octop_home: Path) -> AsyncIterator[tuple[httpx.AsyncClient, Any, dict[str, Any]]]:
    """admin (KB owner) · bob (project viewer) · carol (outsider), one bound project."""
    async with octop_client(tmp_octop_home) as (client, srv):
        await bootstrap_admin(client, tmp_octop_home)
        admin = await auth_header(client)
        bob = await create_user(client, admin, username="bob")
        carol = await create_user(client, admin, username="carol")
        bob_id = await resolve_user_id(client, admin, "bob")

        bound_kb = str(srv.services.knowledge_repo.create_base(owner_user_id=1, name="绑定KB").id)
        free_kb = str(srv.services.knowledge_repo.create_base(owner_user_id=1, name="未绑定KB").id)
        project = (
            await client.post(PROJECTS, headers=admin, json={"name": "P1", "status": "active"})
        ).json()
        pid = project["project_id"]
        # The project owns the binding; bob is only a viewer (PROJECT_READ, no write).
        assert srv.services.project_repo.set_kb_id(pid, bound_kb) is None
        added = await client.post(
            f"{PROJECTS}/{pid}/members",
            headers=admin,
            json={"subject_type": "user", "subject_id": str(bob_id), "role": "viewer"},
        )
        assert added.status_code == 201, added.text
        yield (
            client,
            srv,
            {
                "admin": admin,
                "bob": bob,
                "carol": carol,
                "pid": pid,
                "bound_kb": bound_kb,
                "free_kb": free_kb,
            },
        )


async def test_a_project_member_may_read_the_bound_base(
    env: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """① owner-bypass is absent for bob: he reads it *through* the project binding."""
    client, _, ctx = env
    response = await client.get(f"{KB}/{ctx['bound_kb']}", headers=ctx["bob"])
    assert response.status_code == 200, response.text
    assert response.json()["id"] == ctx["bound_kb"]
    # The document list is the tree's data source and uses the same fallback.
    listed = await client.get(f"{KB}/{ctx['bound_kb']}/documents", headers=ctx["bob"])
    assert listed.status_code == 200, listed.text
    assert isinstance(listed.json(), list)


async def test_a_non_member_is_refused(
    env: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """② carol is not a project member → the pre-existing refusal code, never 500."""
    client, _, ctx = env
    for path in (f"{KB}/{ctx['bound_kb']}", f"{KB}/{ctx['bound_kb']}/documents"):
        response = await client.get(path, headers=ctx["carol"])
        assert response.status_code == 403, response.text
        assert response.status_code != 500
        assert response.json()["error"]["code"] == FORBIDDEN


async def test_a_member_of_a_project_without_the_binding_is_refused(
    env: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """③ A7: membership alone is not enough — the *binding* must exist today."""
    client, srv, ctx = env
    # bob is bound-readable first, so the next assertion cannot pass by accident.
    assert (await client.get(f"{KB}/{ctx['bound_kb']}", headers=ctx["bob"])).status_code == 200

    unbound = await client.get(f"{KB}/{ctx['free_kb']}", headers=ctx["bob"])
    assert unbound.status_code == 403, unbound.text
    assert unbound.status_code != 500
    assert unbound.json()["error"]["code"] == FORBIDDEN

    # Unbinding the project drops the access again: no historical binding is kept.
    srv.services.project_repo.set_kb_id(ctx["pid"], None)
    after = await client.get(f"{KB}/{ctx['bound_kb']}", headers=ctx["bob"])
    assert after.status_code == 403, after.text
    assert after.json()["error"]["code"] == FORBIDDEN


async def test_an_archived_project_still_grants_read(
    env: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """④ A3 is frozen: archiving is read-only, **not** unreadable.

    The predicate filters on ``PROJECT_READ`` only; a status filter would break this.
    """
    client, _, ctx = env
    archived = await client.patch(
        f"{PROJECTS}/{ctx['pid']}", headers=ctx["admin"], json={"status": "archived"}
    )
    assert archived.status_code == 200, archived.text
    still = await client.get(f"{KB}/{ctx['bound_kb']}", headers=ctx["bob"])
    assert still.status_code == 200, still.text
    # …while writes stay closed to a viewer anyway (the write gate is untouched).
    write = await client.post(
        f"{KB}/{ctx['bound_kb']}/folders", headers=ctx["bob"], json={"path": "nope"}
    )
    assert write.status_code in (403, 404), write.text
    assert write.status_code != 500
