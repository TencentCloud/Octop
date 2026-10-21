"""Remote Phone device errors follow the request language without real adb calls."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from octop.api.deps import current_user
from octop.api.routers.mobile import status
from octop.infra.users.identity import Role, User


@pytest.mark.parametrize(
    ("language", "chinese"),
    [("zh-CN", True), ("en-US", False), (None, True), ("fr-FR", False)],
)
@pytest.mark.parametrize(
    ("method", "path", "body", "code", "english", "translated"),
    [
        (
            "GET",
            "/mobile/devices/%20/info",
            None,
            400,
            "device is required",
            "设备不能为空",
        ),
        (
            "GET",
            "/mobile/devices/test-serial/info",
            None,
            404,
            "adb device not connected: test-serial",
            "adb 设备未连接：test-serial",
        ),
        (
            "PUT",
            "/mobile/agent-control",
            {"enabled": True},
            400,
            "device is required when enabling",
            "启用时必须指定设备",
        ),
        (
            "PUT",
            "/mobile/agent-control",
            {"enabled": True, "device": "test-serial"},
            400,
            "adb device not connected: test-serial",
            "adb 设备未连接：test-serial",
        ),
    ],
)
def test_mobile_device_errors_use_request_locale(
    monkeypatch: pytest.MonkeyPatch,
    language: str | None,
    chinese: bool,
    method: str,
    path: str,
    body: dict[str, object] | None,
    code: int,
    english: str,
    translated: str,
) -> None:
    monkeypatch.setattr(status, "list_devices", Mock(return_value=[]))
    monkeypatch.setattr(status, "device_info", Mock(return_value={}))
    set_control = Mock()
    monkeypatch.setattr(status, "set_mobile_agent_control", set_control)
    app = FastAPI()
    app.include_router(status.router, prefix="/api")
    user = User(id=1, username="user", role=Role.USER, display_name=None, permissions=["mobile"])
    app.dependency_overrides[current_user] = lambda: user

    with TestClient(app) as client:
        response = client.request(
            method,
            f"/api{path}",
            json=body,
            headers={"Accept-Language": language} if language else {},
        )

    assert response.status_code == code
    assert response.json() == {"detail": translated if chinese else english}
    set_control.assert_not_called()


@pytest.mark.parametrize("enabled", [True, False])
def test_mobile_binding_success_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    enabled: bool,
) -> None:
    device = "test-serial" if enabled else None
    monkeypatch.setattr(status, "list_devices", Mock(return_value=["test-serial"]))
    set_control = Mock()
    monkeypatch.setattr(status, "set_mobile_agent_control", set_control)
    monkeypatch.setattr(
        status,
        "get_mobile_agent_control",
        lambda: SimpleNamespace(enabled=enabled, device=device),
    )
    app = FastAPI()
    app.include_router(status.router, prefix="/api")
    user = User(id=1, username="user", role=Role.USER, display_name=None, permissions=["mobile"])
    app.dependency_overrides[current_user] = lambda: user

    with TestClient(app) as client:
        response = client.put(
            "/api/mobile/agent-control",
            json={"enabled": enabled, "device": " test-serial "},
            headers={"Accept-Language": "zh-CN"},
        )

    assert response.status_code == 200
    assert response.json() == {"enabled": enabled, "device": device}
    set_control.assert_called_once_with(enabled=enabled, device=device)
