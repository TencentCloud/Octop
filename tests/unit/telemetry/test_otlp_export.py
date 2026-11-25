"""End-to-end OTLP/HTTP export against a local fake collector."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from octop.infra.telemetry import init_telemetry, record_inference_usage, shutdown_telemetry


class _Collector(ThreadingHTTPServer):
    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.requests: list[tuple[str, str, bytes]] = []


class _Handler(BaseHTTPRequestHandler):
    server: _Collector

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.server.requests.append((self.path, self.headers.get("Content-Type", ""), body))
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture
def collector() -> Iterator[_Collector]:
    server = _Collector()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture(autouse=True)
def _reset_telemetry() -> Iterator[None]:
    shutdown_telemetry()
    yield
    shutdown_telemetry()


def _closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_otlp_http_export_roundtrip(collector: _Collector, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", f"http://127.0.0.1:{collector.server_port}")
    monkeypatch.setenv("OTEL_METRIC_EXPORT_INTERVAL", "100")
    assert init_telemetry() is True
    record_inference_usage(
        agent_id="a1",
        source="chat",
        provider="",
        request_model="m",
        response_model="m",
        input_tokens=10,
        output_tokens=2,
    )
    shutdown_telemetry()

    assert collector.requests, "collector received no export"
    path, content_type, body = collector.requests[-1]
    assert path == "/v1/metrics"
    assert content_type == "application/x-protobuf"
    assert b"gen_ai.client.inference.usage.input_tokens" in body
    assert b"gen_ai.agent.id" in body


def test_unreachable_collector_does_not_raise_or_hang(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", f"http://127.0.0.1:{_closed_port()}")
    monkeypatch.setenv("OTEL_METRIC_EXPORT_INTERVAL", "100")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TIMEOUT", "2")
    assert init_telemetry() is True
    record_inference_usage(
        agent_id="a1",
        source="chat",
        provider="",
        request_model="m",
        response_model="m",
        input_tokens=10,
        output_tokens=2,
    )
    started = time.monotonic()
    shutdown_telemetry()
    assert time.monotonic() - started < 15
