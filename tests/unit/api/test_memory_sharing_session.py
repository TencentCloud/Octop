"""共享记忆（memory sharing）会话负载的单测。

覆盖点：
- 未连接时只回 ``{"connected": False}``，不带任何空间信息；
- 已连接时回空间/权限/过期时间，并带上客户端接入指引要用的 ``base_url``；
- ``base_url`` 尊重 ``OCTOP_MEMORY_SERVICE_URL`` 且去掉尾部斜杠（拼接 MCP 地址时不会出现双斜杠）。

这些字段是「共享记忆」页签 S3（客户端接入指引）的数据来源，缺失会让面板没法显示 MCP 地址。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from octop.api.routers import memory_mcp
from octop.api.routers import memory_sharing as router_module
from octop.infra.agents import memory_sharing
from octop.infra.errors import ErrorCode, OctopError


def _session() -> memory_sharing.SharingSession:
    return memory_sharing.SharingSession(
        token="msess_test",
        space_id="project-alpha",
        scopes=("read", "write"),
        expires_at="2099-01-01T00:00:00+00:00",
        stored_at=0.0,
    )


def test_payload_without_session_is_disconnected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(memory_sharing, "get_session", lambda user_id: None)

    payload = router_module._session_payload(7)

    assert payload == {"connected": False}


def test_payload_carries_space_scopes_and_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(memory_sharing, "get_session", lambda user_id: _session())
    monkeypatch.setenv("OCTOP_MEMORY_SERVICE_URL", "http://memory.internal:8790/")

    payload = router_module._session_payload(7)

    assert payload["connected"] is True
    assert payload["space_id"] == "project-alpha"
    assert payload["scopes"] == ["read", "write"]
    assert payload["expires_at"] == "2099-01-01T00:00:00+00:00"
    # 尾斜杠必须被去掉，面板拼 f"{base_url}/mcp/" 才不会出现 "//mcp/"
    assert payload["base_url"] == "http://memory.internal:8790"


def test_base_url_falls_back_to_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OCTOP_MEMORY_SERVICE_URL", raising=False)

    assert memory_sharing.service_url() == "http://127.0.0.1:8790"


def test_upstream_401_asks_for_reconnect() -> None:
    """F2：上游 401 不能被报成「请求参数错」，要提示重连。"""
    import httpx

    response = httpx.Response(
        401, json={"detail": "session expired"}, request=httpx.Request("GET", "http://x/")
    )
    error = memory_sharing._upstream_error(response)

    assert error.code == ErrorCode.FORBIDDEN
    assert error.details["needs_reconnect"] is True


def test_upstream_404_is_not_found() -> None:
    import httpx

    response = httpx.Response(
        404, json={"detail": "no space"}, request=httpx.Request("GET", "http://x/")
    )
    error = memory_sharing._upstream_error(response)

    assert error.code == ErrorCode.NOT_FOUND


def test_space_binding_conflict_stops_token_issuance(monkeypatch: pytest.MonkeyPatch) -> None:
    expert = {
        "agent_id": "alpha",
        "space_id": "project-alpha",
        "name": "Alpha",
        "usable": True,
        "backend": "sqlite",
        "backend_config": {"db_path": "alpha.db"},
    }
    monkeypatch.setattr(memory_mcp, "_experts", lambda server, user: [expert])
    monkeypatch.setattr(memory_sharing, "get_session", lambda user_id: _session())
    paths: list[str] = []

    def conflict(client: httpx.Client, method: str, url: str, **kwargs: object) -> httpx.Response:
        request = httpx.Request(method, url)
        paths.append(request.url.path)
        return httpx.Response(
            409, json={"detail": "space is bound to different storage"}, request=request
        )

    monkeypatch.setattr(httpx.Client, "request", conflict)
    with pytest.raises(OctopError) as caught:
        memory_mcp.create_token(
            memory_mcp.TokenCreateBody(name="codex", expert_ids=["alpha"]),
            user=SimpleNamespace(id=7),
            server=SimpleNamespace(),
        )
    assert caught.value.status == 409
    assert caught.value.code == ErrorCode.MEMORY_SERVICE_CONFLICT
    assert paths == ["/api/admin/spaces"]


def test_unknown_scope_is_rejected() -> None:
    """F4：scopes 只允许 read/write。"""
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        router_module.TokenCreateBody(client_name="codex", scopes=["read", "admin"])


def test_empty_scopes_fall_back_to_read_write() -> None:
    body = router_module.TokenCreateBody(client_name="codex", scopes=[])
    assert body.scopes == ["read", "write"]


def test_require_session_adopts_persisted_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """F1：进程重启后（内存里没有会话）任意接口都应先恢复持久化会话。"""
    memory_sharing.clear_session(7)
    monkeypatch.setattr(
        router_module,
        "open_text",
        lambda repo, purpose, sealed: json.dumps(
            {
                "token": "msess_restored",
                "space_id": "project-alpha",
                "scopes": ["read"],
                "expires_at": "2099-01-01T00:00:00+00:00",
                "stored_at": 0.0,
            }
        ),
    )

    repos = SimpleNamespace(
        settings_repo=SimpleNamespace(get=lambda key: "sealed"),
        secret_repo=SimpleNamespace(),
    )
    server = SimpleNamespace(services=SimpleNamespace(repos=repos))

    router_module._require_session(server, 7)

    restored = memory_sharing.get_session(7)
    assert restored is not None
    assert restored.token == "msess_restored"
    memory_sharing.clear_session(7)


def test_save_session_reports_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """F3：没存成功要能告诉调用方，不能静默。"""
    server = SimpleNamespace(services=None)
    assert router_module._save_session(server, 7, _session()) is False


def test_install_script_is_pinned_and_carries_no_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """R1/R7：安装脚本由 Octop 托管、来源固定 tag、GET 不产生任何凭证。"""
    monkeypatch.delenv("OCTOP_MEMORY_INSTALLER_URL", raising=False)
    monkeypatch.setenv("OCTOP_MEMORY_SERVICE_URL", "http://memory.internal:8790")

    body = router_module.install_script_body("http://memory.internal:8790/mcp/")

    assert "v1.0.11" in body  # 固定 tag，不是 main
    assert "raw.githubusercontent.com" in body
    assert "/main/" not in body
    assert "http://memory.internal:8790/mcp/" in body
    assert "mcp_" not in body  # 不夹带任何 token
    assert "OCTOP_MEMORY_INSTALLER_URL" in body  # 可指向内网镜像


def test_install_script_honours_mirror_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTOP_MEMORY_INSTALLER_URL", "http://octop.internal/mirror/install.sh")

    body = router_module.install_script_body("http://memory.internal:8790/mcp/")

    assert "http://octop.internal/mirror/install.sh" in body
    assert "raw.githubusercontent.com" not in body
