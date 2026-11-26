"""record_http_request attributes and the HTTP metrics middleware."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import APIRouter, FastAPI, WebSocket
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient

from octop.api.middleware.http_metrics import install
from octop.infra.telemetry import record_http_request
from tests.support.otel import active_telemetry, metric_points

NAME = "http.server.request.duration"


def test_record_http_request_attributes() -> None:
    with active_telemetry() as reader:
        record_http_request(
            method="get",
            scheme="https",
            duration_s=0.2,
            route="/api/agents/{agent_id}",
            status_code=503,
            error_type="503",
        )
        (point,) = metric_points(reader, NAME)
    assert dict(point.attributes) == {
        "http.request.method": "GET",
        "url.scheme": "https",
        "http.route": "/api/agents/{agent_id}",
        "http.response.status_code": 503,
        "error.type": "503",
    }


def test_unknown_method_collapses_and_blank_fields_are_omitted() -> None:
    with active_telemetry() as reader:
        record_http_request(method="BREW", scheme="", duration_s=0.01)
        (point,) = metric_points(reader, NAME)
    assert dict(point.attributes) == {"http.request.method": "_OTHER", "url.scheme": "http"}


def test_negative_duration_and_inactive_telemetry_are_ignored() -> None:
    record_http_request(method="GET", scheme="http", duration_s=0.1)
    with active_telemetry() as reader:
        record_http_request(method="GET", scheme="http", duration_s=-1)
        assert metric_points(reader, NAME) == []


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()

    @app.get("/items/{item_id}")
    async def item(item_id: str) -> dict[str, str]:
        return {"id": item_id}

    @app.get("/files/{name:path}")
    async def files(name: str) -> dict[str, str]:
        return {"name": name}

    @app.get("/unavailable")
    async def unavailable() -> JSONResponse:
        return JSONResponse({"detail": "down"}, status_code=503)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("kaput")

    @app.get("/stream")
    async def stream() -> StreamingResponse:
        async def body() -> AsyncIterator[bytes]:
            yield b"a"
            yield b"b"

        return StreamingResponse(body())

    nested = APIRouter(prefix="/agents/{agent_id}/memory")

    @nested.get("/x/{rest:path}")
    async def nested_route(agent_id: str, rest: str) -> dict[str, str]:
        return {"agent": agent_id, "rest": rest}

    app.include_router(nested, prefix="/api")

    @app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:
        await socket.accept()
        await socket.close()

    install(app)
    yield TestClient(app, raise_server_exceptions=False)


def _by_status(reader: object) -> dict[tuple[str, int | None], object]:
    return {
        (p.attributes.get("http.route", ""), p.attributes.get("http.response.status_code")): p
        for p in metric_points(reader, NAME)  # type: ignore[arg-type]
    }


def test_route_template_keeps_cardinality_low(client: TestClient) -> None:
    with active_telemetry() as reader:
        assert client.get("/items/1").status_code == 200
        assert client.get("/items/2").status_code == 200
        points = _by_status(reader)
    assert list(points) == [("/items/{item_id}", 200)]
    assert points[("/items/{item_id}", 200)].count == 2  # type: ignore[attr-defined]


def test_unmatched_path_has_no_route_attribute(client: TestClient) -> None:
    with active_telemetry() as reader:
        assert client.get("/nope/123").status_code == 404
        (point,) = metric_points(reader, NAME)
    assert "http.route" not in point.attributes
    assert point.attributes["http.response.status_code"] == 404
    assert "error.type" not in point.attributes  # 4xx is not a server error


def test_5xx_response_sets_error_type_to_status(client: TestClient) -> None:
    with active_telemetry() as reader:
        client.get("/unavailable")
        (point,) = metric_points(reader, NAME)
    assert point.attributes["error.type"] == "503"
    assert point.attributes["http.route"] == "/unavailable"


def test_unhandled_exception_is_a_500_with_exception_type(client: TestClient) -> None:
    with active_telemetry() as reader:
        assert client.get("/boom").status_code == 500
        (point,) = metric_points(reader, NAME)
    assert point.attributes["http.response.status_code"] == 500
    assert point.attributes["error.type"] == "RuntimeError"


def test_streaming_response_is_timed_to_the_end(client: TestClient) -> None:
    with active_telemetry() as reader:
        assert client.get("/stream").text == "ab"
        (point,) = metric_points(reader, NAME)
    assert point.count == 1
    assert point.attributes["http.route"] == "/stream"


def test_websocket_connections_are_not_recorded(client: TestClient) -> None:
    with active_telemetry() as reader:
        with client.websocket_connect("/ws"):
            pass
        assert metric_points(reader, NAME) == []


def test_included_router_prefixes_and_converters_stay_in_the_template(
    client: TestClient,
) -> None:
    with active_telemetry() as reader:
        assert client.get("/api/agents/7/memory/x/a/b").status_code == 200
        assert client.get("/api/agents/8/memory/x/c").status_code == 200
        (point,) = metric_points(reader, NAME)
    assert point.count == 2
    assert point.attributes["http.route"] == "/api/agents/{agent_id}/memory/x/{rest}"


def test_top_level_path_converter_is_normalised(client: TestClient) -> None:
    with active_telemetry() as reader:
        assert client.get("/files/a/b/c.txt").status_code == 200
        (point,) = metric_points(reader, NAME)
    assert point.attributes["http.route"] == "/files/{name}"
