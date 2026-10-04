"""Bridge tunnel allowlist must police the path the ASGI app actually receives.

``execute_local_http`` feeds the peer-supplied path straight to
``httpx.ASGITransport``, whose scope ``path`` is ``httpx.URL.path`` — i.e. the
dot-segments are already resolved by the time the local FastAPI router sees
them. The allowlist therefore has to resolve them too, otherwise an allowed
prefix such as ``/api/agents/<id>/threads`` launders a request to any
local-only route (``/admin/audit-log``, ``/settings``, ``/setup/*``).
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from octop.infra.bridge.tunnel_policy import is_tunnel_path_allowed

# Every ``resolved`` entry is a real local-only route on the peer: spelled
# directly each one is denied, so a policy that resolves the traversal would
# have to keep denying it.
TRAVERSALS: list[tuple[str, str, str]] = [
    (
        "GET",
        "/api/agents/01ABC/threads/../../../../admin/audit-log",
        "/admin/audit-log",
    ),
    ("PATCH", "/api/agents/01ABC/config/../../../../settings", "/settings"),
    ("GET", "/api/mbti/../../users", "/users"),
    (
        "GET",
        "/api/subagent-catalog/../../bridge/connections",
        "/bridge/connections",
    ),
    ("GET", "/api/agents/01ABC/threads/../../../../setup/status", "/setup/status"),
    ("GET", "/api/agents/01ABC/uploads/../../../auth/login", "/api/auth/login"),
]


@pytest.mark.parametrize(("method", "path", "resolved"), TRAVERSALS)
def test_dot_segments_cannot_reach_local_only_routes(method: str, path: str, resolved: str) -> None:
    # Precondition: the destination really is local-only when spelled directly.
    assert not is_tunnel_path_allowed(method, resolved)
    assert not is_tunnel_path_allowed(method, httpx.URL(path).path)
    # The traversal must not smuggle it through either.
    assert not is_tunnel_path_allowed(method, path)


@pytest.mark.parametrize(("method", "path", "resolved"), TRAVERSALS)
def test_traversal_is_rejected_end_to_end(method: str, path: str, resolved: str) -> None:
    """Drive the same guard-then-httpx order as ``execute_local_http``."""
    seen: list[str] = []

    async def app(scope, receive, send):  # noqa: ANN001, ANN202
        seen.append(scope["path"])
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def run() -> None:
        if not is_tunnel_path_allowed(method, path):
            return  # execute_local_http raises BRIDGE_REMOTE_UNSUPPORTED here
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://bridge.local",
            timeout=5.0,
        ) as client:
            await client.request(method, path)

    asyncio.run(run())
    # The local router must never be reached with a local-only path.
    assert seen == []
    assert resolved not in seen


def test_baseline_traversal_really_would_have_reached_the_router() -> None:
    """Pin the premise: without the fix, ``httpx`` hands the *resolved* path on.

    This is what makes the guard's dot-segment handling load-bearing rather
    than defence in depth — the ASGI scope path is the resolved one, so an
    unresolved guard really does route ``/admin/audit-log`` to the local app.
    """
    seen: list[str] = []

    async def app(scope, receive, send):  # noqa: ANN001, ANN202
        seen.append(scope["path"])
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://bridge.local",
            timeout=5.0,
        ) as client:
            await client.request("GET", "/api/agents/01ABC/threads/../../../../admin/audit-log")

    asyncio.run(run())
    assert seen == ["/admin/audit-log"]


def test_dot_segments_that_stay_inside_the_allowlist_are_allowed() -> None:
    """Traversal is only a problem when it escapes; these resolve in-place.

    ``httpx`` drops ``.`` and pops ``..`` for these too, and the resolved
    targets are ordinary agent-scoped resources, so the allowlist must keep
    accepting them rather than blanket-refusing every dotted path.
    """
    for method, path, resolved in [
        ("GET", "/api/agents/01ABC/threads/..", "/api/agents/01ABC"),
        ("GET", "/api/agents/./01ABC/threads", "/api/agents/01ABC/threads"),
        ("GET", "/api/agents/01ABC/threads/../history", "/api/agents/01ABC/history"),
        ("GET", "/api/agents/../agents/01ABC", "/api/agents/01ABC"),
    ]:
        assert is_tunnel_path_allowed(method, resolved), resolved
        assert is_tunnel_path_allowed(method, path), path


def test_dot_segments_escaping_the_allowlist_are_rejected() -> None:
    """These resolve onto a local-only route (or above the root) — never allowed."""
    for method, path in [
        ("GET", "/api/mbti/.."),  # resolves to the app root
        ("GET", "/api/agents/01ABC/threads/../../../../admin"),
        ("GET", "/api/subagent-catalog/a/../../b/../.."),  # walks above the root
    ]:
        assert not is_tunnel_path_allowed(method, path), path


def test_allowed_paths_still_resolve_to_themselves() -> None:
    """The fix must not reject legitimate nested agent resources."""
    for method, path in [
        ("GET", "/api/agents/01ABC"),
        ("GET", "/api/agents/01ABC/threads"),
        ("GET", "/api/agents/01ABC/history/versions"),
        ("POST", "/api/agents/01ABC/uploads"),
        ("PATCH", "/api/agents/01ABC/tool-settings/shell"),
        ("GET", "/api/subagent-catalog/divisions"),
    ]:
        assert is_tunnel_path_allowed(method, path), path
        assert is_tunnel_path_allowed(method, httpx.URL(path).path), path
