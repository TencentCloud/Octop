"""Unit tests for the WebSocket-upgrade gate in the bridge proxy middleware."""

from __future__ import annotations

import pytest

from octop.api.middleware.bridge_proxy import _is_websocket_upgrade


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({}, False),
        # A reverse proxy that pins Connection: upgrade on every request is not a handshake.
        ({"connection": "upgrade"}, False),
        ({"connection": "upgrade", "upgrade": "websocket"}, True),
        ({"connection": "keep-alive, Upgrade", "upgrade": "WebSocket"}, True),
        ({"connection": "Upgrade", "upgrade": "h2c"}, False),
        ({"connection": "keep-alive", "upgrade": "websocket"}, False),
        ({"connection": "keep-alive, upgrade", "upgrade": "websocket, h2c"}, False),
    ],
)
def test_is_websocket_upgrade(headers: dict[str, str], expected: bool) -> None:
    assert _is_websocket_upgrade(headers) is expected


class _StubPeerResponse:
    status_code = 200
    content = b"TUNNELED"
    headers = {"content-type": "text/plain"}


class _StubBridgeManager:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def tunnel_http(self, **kwargs: object) -> _StubPeerResponse:
        self.calls.append(kwargs)
        return _StubPeerResponse()


def _app_with_bridge() -> tuple[object, _StubBridgeManager]:
    from types import SimpleNamespace

    from fastapi import FastAPI

    from octop.api.middleware.bridge_proxy import install

    manager = _StubBridgeManager()
    server = SimpleNamespace(app_runtime=SimpleNamespace(bridge_manager=manager))
    app = FastAPI()

    @app.get("/api/agents/bridge:cid1:aid1/threads")
    def _local_route() -> str:
        return "NEXT"

    install(app, server)

    @app.middleware("http")
    async def _inject_user(request, call_next):  # type: ignore[no-untyped-def]
        request.state.octop_user = SimpleNamespace(id=7)
        return await call_next(request)

    return app, manager


def test_proxy_upgrade_connection_header_alone_still_tunnels() -> None:
    from starlette.testclient import TestClient

    app, manager = _app_with_bridge()
    with TestClient(app) as client:
        response = client.get(
            "/api/agents/bridge:cid1:aid1/threads",
            headers={"connection": "upgrade"},
        )
    assert response.text == "TUNNELED"
    assert manager.calls, "bridge request must reach the tunnel"


def test_proxy_real_websocket_handshake_bypasses_to_router() -> None:
    from starlette.testclient import TestClient

    app, manager = _app_with_bridge()
    with TestClient(app) as client:
        response = client.get(
            "/api/agents/bridge:cid1:aid1/threads",
            headers={"connection": "upgrade", "upgrade": "websocket"},
        )
    assert response.json() == "NEXT"
    assert manager.calls == []
