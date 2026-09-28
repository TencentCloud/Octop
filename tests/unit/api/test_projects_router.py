"""HTTP contract for the projects router (plan T1.4 acceptance).

Checks what the plan asks a reviewer to eyeball in ``/api/docs``: the tag exists
with a description, every route carries a summary, and every route declares a
typed response model rather than an untyped blob.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from tests.support.app import ensure_control_plane_bound, write_octop_config

from octop.api.app import build_app
from octop.api.routers import projects as projects_router
from octop.infra.server import OctopServer

EXPECTED_PATHS = {
    "/api/projects",
    "/api/projects/{project_id}",
    "/api/projects/{project_id}/members",
    "/api/projects/{project_id}/members/{subject_type}/{subject_id}",
    "/api/projects/{project_id}/tasks",
    "/api/projects/{project_id}/tasks/{task_id}",
    "/api/projects/{project_id}/timeline",
}


async def test_projects_openapi_contract(tmp_octop_home: Path) -> None:
    write_octop_config(tmp_octop_home, enable_api_docs=True)
    srv = OctopServer(home=tmp_octop_home)
    await srv.start()
    await ensure_control_plane_bound(srv)
    try:
        app = build_app(srv)
        with TestClient(app) as c:
            spec = c.get("/api/openapi.json").json()
    finally:
        await srv.stop()

    tags = {t["name"]: t.get("description", "") for t in spec.get("tags", [])}
    assert "projects" in tags, "the projects tag must be registered"
    assert tags["projects"].strip(), "the projects tag needs a description"

    paths = {p for p in spec["paths"] if p.startswith("/api/projects")}
    missing = EXPECTED_PATHS - paths
    assert not missing, f"missing paths: {sorted(missing)}"

    for path, operations in spec["paths"].items():
        if not path.startswith("/api/projects"):
            continue
        for method, op in operations.items():
            if method not in {"get", "post", "patch", "delete"}:
                continue
            assert op.get("summary", "").strip(), f"{method.upper()} {path} has no summary"
            assert "projects" in op.get("tags", []), f"{method.upper()} {path} missing tag"

            ok = op["responses"].get("200") or op["responses"].get("201")
            assert ok is not None, f"{method.upper()} {path} has no 2xx response"
            # JSON where the route returns a model; a declared binary media type for
            # the file download (which must still be *typed*, not an empty card).
            content = ok.get("content", {})
            declared = content.get("application/json") or next(iter(content.values()), {})
            assert declared.get("schema"), f"{method.upper()} {path} has an untyped response"


def test_every_route_requires_the_projects_permission() -> None:
    """The coarse gate is the first line of defence; the role check is the second."""
    for route in projects_router.router.routes:
        dependant = getattr(route, "dependant", None)
        assert dependant is not None
        names = {getattr(dep.call, "__name__", "") for dep in _walk(dependant)}
        assert "_dep" in names, f"{route.path} is not behind require_permission()"


def _walk(dependant: Any) -> list[Any]:
    out = list(dependant.dependencies)
    for dep in list(out):
        out.extend(_walk(dep))
    return out
