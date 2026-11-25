"""OctopServer boots and stops OpenTelemetry metrics."""

from __future__ import annotations

from pathlib import Path

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from octop.infra.server import OctopServer
from octop.infra.telemetry import (
    init_telemetry,
    is_active,
    record_inference_usage,
    shutdown_telemetry,
)
from tests.support.app import octop_client, seed_cached_general_assistant
from tests.support.auth import auth_header, bootstrap_admin
from tests.support.otel import metric_points


async def test_server_wires_telemetry_bindings_and_shuts_it_down(
    tmp_octop_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shutdown_telemetry()
    reader = InMemoryMetricReader()
    assert init_telemetry(environ={}, reader=reader) is True
    try:
        async with octop_client(tmp_octop_home) as (client, srv):
            await bootstrap_admin(client, tmp_octop_home)
            assert srv.app_runtime is not None
            rows = srv.app_runtime.agent_registry.list_rows()
            assert rows, "bootstrap should create the default agent"

            (gauge,) = metric_points(reader, "octop.agent.active")
            assert gauge.value == len(rows)

            record_inference_usage(
                agent_id=rows[0].agent_id,
                source="chat",
                provider="",
                request_model="m",
                response_model="m",
                input_tokens=3,
                output_tokens=1,
            )
            names = {
                p.attributes.get("gen_ai.agent.name")
                for p in metric_points(reader, "gen_ai.client.inference.usage.input_tokens")
            }
            assert names == {rows[0].name}
        assert is_active() is False
    finally:
        shutdown_telemetry()


async def test_server_start_activates_telemetry_from_env_and_stop_deactivates(
    tmp_octop_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:1")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TIMEOUT", "1")
    shutdown_telemetry()
    try:
        async with octop_client(tmp_octop_home):
            assert is_active() is True
        assert is_active() is False
    finally:
        shutdown_telemetry()


async def test_embedded_start_does_not_activate_telemetry(
    tmp_octop_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:1")
    shutdown_telemetry()
    seed_cached_general_assistant(tmp_octop_home)
    srv = OctopServer(home=tmp_octop_home)
    await srv.start(serve_background=False)
    try:
        assert is_active() is False
    finally:
        await srv.stop()
        shutdown_telemetry()


async def test_failed_start_leaves_telemetry_inactive(
    tmp_octop_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:1")
    shutdown_telemetry()
    seed_cached_general_assistant(tmp_octop_home)
    monkeypatch.setattr("octop.infra.server.should_defer_control_plane_db", lambda *_a: False)

    async def boom(self: OctopServer, config: object) -> None:
        raise RuntimeError("control plane exploded")

    monkeypatch.setattr(OctopServer, "_open_control_plane", boom)
    srv = OctopServer(home=tmp_octop_home)
    try:
        with pytest.raises(RuntimeError, match="exploded"):
            await srv.start()
        assert is_active() is False
    finally:
        shutdown_telemetry()


async def test_real_app_records_http_requests_by_route_template(tmp_octop_home: Path) -> None:
    shutdown_telemetry()
    reader = InMemoryMetricReader()
    assert init_telemetry(environ={}, reader=reader) is True
    try:
        async with octop_client(tmp_octop_home) as (client, srv):
            await bootstrap_admin(client, tmp_octop_home)
            assert srv.app_runtime is not None
            agent_id = srv.app_runtime.agent_registry.list_rows()[0].agent_id
            before = len(metric_points(reader, "http.server.request.duration"))
            headers = await auth_header(client)
            ok = await client.get(f"/api/agents/{agent_id}", headers=headers)
            missing = await client.get("/api/agents/does-not-exist", headers=headers)
            assert ok.status_code == 200
            assert missing.status_code == 404
            points = metric_points(reader, "http.server.request.duration")
        assert len(points) > before
        routes = {
            (p.attributes.get("http.route"), p.attributes.get("http.response.status_code"))
            for p in points
        }
        assert ("/api/agents/{agent_id}", 200) in routes
        assert ("/api/agents/{agent_id}", 404) in routes
        # The raw agent id must never leak into a label.
        assert not any(agent_id in str(p.attributes) for p in points)
    finally:
        shutdown_telemetry()
