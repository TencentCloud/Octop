"""Provider lifecycle, activation rules and resource attributes."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from opentelemetry.sdk.metrics.export import (
    InMemoryMetricReader,
    MetricExporter,
    MetricExportResult,
    PeriodicExportingMetricReader,
)

from octop.infra.telemetry import (
    bind_active_agents,
    init_telemetry,
    is_active,
    shutdown_telemetry,
)
from octop.infra.telemetry import setup as telemetry_setup

_ENDPOINT = {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:1"}


@pytest.fixture(autouse=True)
def _reset_telemetry(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Endpoint tests point at a dead port; keep exporter retries short.
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TIMEOUT", "1")
    shutdown_telemetry()
    yield
    shutdown_telemetry()


def _resource_attributes(reader: InMemoryMetricReader) -> dict[str, object]:
    instruments = telemetry_setup._instruments()
    assert instruments is not None
    instruments.counters["messages_total"].add(1)
    data = reader.get_metrics_data()
    assert data is not None
    return dict(data.resource_metrics[0].resource.attributes)


def test_inactive_without_endpoint() -> None:
    assert init_telemetry(environ={}) is False
    assert is_active() is False


def test_active_with_endpoint() -> None:
    assert init_telemetry(environ=_ENDPOINT) is True
    assert is_active() is True


def test_metrics_specific_endpoint_activates() -> None:
    env = {"OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": "http://127.0.0.1:1/v1/metrics"}
    assert init_telemetry(environ=env) is True


def test_sdk_disabled_wins_over_endpoint() -> None:
    env = {**_ENDPOINT, "OTEL_SDK_DISABLED": "TRUE"}
    assert init_telemetry(environ=env) is False
    assert is_active() is False


def test_sdk_disabled_wins_over_injected_reader() -> None:
    env = {"OTEL_SDK_DISABLED": "true"}
    assert init_telemetry(environ=env, reader=InMemoryMetricReader()) is False


def test_injected_reader_activates() -> None:
    assert init_telemetry(environ={}, reader=InMemoryMetricReader()) is True
    assert is_active() is True


@pytest.mark.parametrize("value", ["none", "NONE", " none "])
def test_metrics_exporter_none_disables_export(value: str) -> None:
    env = {**_ENDPOINT, "OTEL_METRICS_EXPORTER": value}
    assert init_telemetry(environ=env) is False
    assert is_active() is False


def test_metrics_exporter_otlp_is_the_default_and_accepted() -> None:
    env = {**_ENDPOINT, "OTEL_METRICS_EXPORTER": "otlp"}
    assert init_telemetry(environ=env) is True


@pytest.mark.parametrize("value", ["console", "prometheus"])
def test_unsupported_metrics_exporter_disables_with_warning(
    value: str, caplog: pytest.LogCaptureFixture
) -> None:
    env = {**_ENDPOINT, "OTEL_METRICS_EXPORTER": value}
    with caplog.at_level("WARNING"):
        assert init_telemetry(environ=env) is False
    assert "OTEL_METRICS_EXPORTER" in caplog.text


@pytest.mark.parametrize(
    "name", ["OTEL_EXPORTER_OTLP_PROTOCOL", "OTEL_EXPORTER_OTLP_METRICS_PROTOCOL"]
)
@pytest.mark.parametrize("value", ["grpc", "http/json"])
def test_unsupported_otlp_protocol_disables_with_warning(
    name: str, value: str, caplog: pytest.LogCaptureFixture
) -> None:
    env = {**_ENDPOINT, name: value}
    with caplog.at_level("WARNING"):
        assert init_telemetry(environ=env) is False
    assert name in caplog.text


def test_http_protobuf_protocol_is_accepted() -> None:
    env = {**_ENDPOINT, "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf"}
    assert init_telemetry(environ=env) is True


def test_resource_and_scope_carry_the_octop_version() -> None:
    import octop

    reader = InMemoryMetricReader()
    init_telemetry(environ={}, reader=reader)
    assert _resource_attributes(reader)["service.version"] == octop.__version__
    data = reader.get_metrics_data()
    assert data is not None
    scope = data.resource_metrics[0].scope_metrics[0].scope
    assert (scope.name, scope.version) == ("octop", octop.__version__)


def test_service_version_env_override() -> None:
    reader = InMemoryMetricReader()
    init_telemetry(environ={"OTEL_RESOURCE_ATTRIBUTES": "service.version=9.9.9"}, reader=reader)
    assert _resource_attributes(reader)["service.version"] == "9.9.9"


def test_init_is_idempotent_while_active() -> None:
    first = InMemoryMetricReader()
    assert init_telemetry(environ={}, reader=first) is True
    before = telemetry_setup._instruments()
    assert init_telemetry(environ={}, reader=InMemoryMetricReader()) is True
    assert telemetry_setup._instruments() is before


def test_default_service_name() -> None:
    reader = InMemoryMetricReader()
    init_telemetry(environ={}, reader=reader)
    assert _resource_attributes(reader)["service.name"] == "octop"


def test_service_name_env_override() -> None:
    reader = InMemoryMetricReader()
    init_telemetry(environ={"OTEL_SERVICE_NAME": "my-octop"}, reader=reader)
    assert _resource_attributes(reader)["service.name"] == "my-octop"


def test_service_name_from_resource_attributes_env() -> None:
    reader = InMemoryMetricReader()
    init_telemetry(
        environ={"OTEL_RESOURCE_ATTRIBUTES": "service.name=other,deployment.environment=dev"},
        reader=reader,
    )
    attrs = _resource_attributes(reader)
    assert attrs["service.name"] == "other"
    assert attrs["deployment.environment"] == "dev"


def test_shutdown_is_idempotent_and_resets() -> None:
    init_telemetry(environ={}, reader=InMemoryMetricReader())
    shutdown_telemetry()
    shutdown_telemetry()
    assert is_active() is False
    assert init_telemetry(environ={}, reader=InMemoryMetricReader()) is True


@pytest.mark.parametrize(
    "bad_env",
    [
        {"OTEL_METRIC_EXPORT_INTERVAL": "0"},
        {"OTEL_EXPORTER_OTLP_TIMEOUT": "10s"},
        {"OTEL_EXPORTER_OTLP_COMPRESSION": "foo"},
    ],
)
def test_malformed_otel_env_disables_export_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch, bad_env: dict[str, str]
) -> None:
    for key, value in bad_env.items():
        monkeypatch.setenv(key, value)
    assert init_telemetry(environ=_ENDPOINT) is False
    assert is_active() is False


class _CapturingExporter(MetricExporter):
    def __init__(self) -> None:
        super().__init__()
        self.exported: list[object] = []

    def export(
        self, metrics_data: object, timeout_millis: float = 10_000, **kwargs: object
    ) -> MetricExportResult:
        self.exported.append(metrics_data)
        return MetricExportResult.SUCCESS

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return True

    def shutdown(self, timeout_millis: float = 30_000, **kwargs: object) -> None:
        return None


def test_final_export_on_shutdown_still_reports_active_agents() -> None:
    exporter = _CapturingExporter()
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=3_600_000)
    init_telemetry(environ={}, reader=reader)
    bind_active_agents(lambda: 4)
    shutdown_telemetry()

    values = [
        point.value
        for data in exporter.exported
        for rm in data.resource_metrics  # type: ignore[attr-defined]
        for sm in rm.scope_metrics
        for metric in sm.metrics
        if metric.name == "octop.agent.active"
        for point in metric.data.data_points
    ]
    assert values == [4]
