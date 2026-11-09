"""Unit tests for OpenAPI schema customization."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from tests.support.app import ensure_control_plane_bound, write_octop_config

from octop.api.app import build_app
from octop.infra.server import OctopServer


async def test_openapi_has_bearer_security_and_descriptions(tmp_octop_home: Path) -> None:
    write_octop_config(tmp_octop_home, enable_api_docs=True)
    srv = OctopServer(home=tmp_octop_home)
    await srv.start()
    await ensure_control_plane_bound(srv)
    try:
        app = build_app(srv)
        with TestClient(app) as c:
            spec = c.get("/api/openapi.json").json()
        assert spec["info"]["description"]
        assert "BearerAuth" in spec["components"]["securitySchemes"]
        login = spec["paths"]["/api/auth/login"]["post"]
        assert login["summary"] == "Sign in"
        me = spec["paths"]["/api/auth/me"]["get"]
        assert "BearerAuth" in me["security"][0]
        assert "security" not in spec["paths"]["/api/setup/status"]["get"]
        extraction = spec["paths"]["/api/agents/{agent_id}/memory/extract-config"]["put"]
        ref = extraction["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        properties = spec["components"]["schemas"][ref.rsplit("/", 1)[-1]]["properties"]
        for key in ("memory_capture_enabled", "memory_recall_inject_enabled"):
            assert {"type": "boolean"} in properties[key]["anyOf"]
            assert properties[key]["description"]
    finally:
        await srv.stop()
