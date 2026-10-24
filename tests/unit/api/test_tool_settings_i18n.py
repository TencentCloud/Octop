"""Tool-settings validation errors follow the request language."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from octop.api.deps import current_user, get_server
from octop.api.routers.agent_tools import router
from octop.infra.users.identity import Role, User


@pytest.mark.parametrize(
    ("language", "chinese"),
    [("zh-CN", True), ("en-US", False), (None, True), ("fr-FR", False)],
)
@pytest.mark.parametrize(
    ("method", "tool", "kind", "body", "english", "translated"),
    [
        (
            "PUT",
            "",
            "team",
            {"disabled_builtin": []},
            "team host tools are fixed to member dispatch",
            "团队主控工具固定为成员派工，不可修改",
        ),
        (
            "PATCH",
            "/web_fetch",
            "team",
            {"enabled": False},
            "team host tools are fixed to member dispatch",
            "团队主控工具固定为成员派工，不可修改",
        ),
        (
            "PATCH",
            "/%20",
            "expert",
            {"enabled": False},
            "tool name is required",
            "工具名称不能为空",
        ),
        (
            "PATCH",
            "/read_file",
            "expert",
            {"enabled": False},
            "tool 'read_file' cannot be disabled",
            "工具 'read_file' 不可禁用",
        ),
        (
            "PATCH",
            "/example",
            "expert",
            {"enabled": False, "source": "plugin"},
            "plugin_id is required for plugin tools",
            "插件工具必须提供 plugin_id",
        ),
    ],
)
def test_tool_settings_errors_use_request_locale(
    language: str | None,
    chinese: bool,
    method: str,
    tool: str,
    kind: str,
    body: dict[str, object],
    english: str,
    translated: str,
) -> None:
    registry = Mock()
    registry.get_row.return_value = SimpleNamespace(user_id=1, kind=kind)
    server = SimpleNamespace(app_runtime=SimpleNamespace(agent_registry=registry))
    user = User(id=1, username="owner", role=Role.USER, display_name=None, permissions=["tools"])
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[current_user] = lambda: user
    app.dependency_overrides[get_server] = lambda: server

    with TestClient(app) as client:
        response = client.request(
            method,
            f"/api/agents/example/tool-settings{tool}",
            json=body,
            headers={"Accept-Language": language} if language else {},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": translated if chinese else english}
    registry.persist_tools_disabled.assert_not_called()
    registry.persist_plugin_tools_config.assert_not_called()
