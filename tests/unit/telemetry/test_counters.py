"""Runtime counters forwarded from ``Metrics`` and the active-agents gauge."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from octop.infra.metrics import Metrics
from octop.infra.telemetry import bind_active_agents, record_counter
from tests.support.otel import active_telemetry, metric_points, points_by_attr


@pytest.fixture
def reader() -> Iterator[InMemoryMetricReader]:
    with active_telemetry() as r:
        yield r


def test_inc_forwards_to_otel(reader: InMemoryMetricReader) -> None:
    m = Metrics()
    m.inc("messages_total", 3)
    (point,) = metric_points(reader, "octop.messages")
    assert point.value == 3
    assert m.snapshot()["messages_total"] == 3


@pytest.mark.parametrize(
    "field,instrument",
    [
        ("messages_total", "octop.messages"),
        ("stream_errors_total", "octop.stream.errors"),
        ("cron_runs_total", "octop.cron.runs"),
        ("cron_errors_total", "octop.cron.errors"),
    ],
)
def test_each_counter_maps_to_its_instrument(
    reader: InMemoryMetricReader, field: str, instrument: str
) -> None:
    Metrics().inc(field, 2)
    (point,) = metric_points(reader, instrument)
    assert point.value == 2


def test_inc_attributes_become_data_point_labels(reader: InMemoryMetricReader) -> None:
    m = Metrics()
    m.inc("messages_total", channel_type="feishu")
    m.inc("messages_total", channel_type="telegram")
    m.inc("messages_total", 2, channel_type="feishu")
    by_channel = points_by_attr(metric_points(reader, "octop.messages"), "octop.channel.type")
    assert by_channel["feishu"].value == 3
    assert by_channel["telegram"].value == 1
    assert m.snapshot()["messages_total"] == 4


def test_error_type_label(reader: InMemoryMetricReader) -> None:
    Metrics().inc("stream_errors_total", error_type="TimeoutError")
    (point,) = metric_points(reader, "octop.stream.errors")
    assert point.attributes == {"error.type": "TimeoutError"}


def test_blank_labels_are_dropped(reader: InMemoryMetricReader) -> None:
    Metrics().inc("messages_total", channel_type="")
    (point,) = metric_points(reader, "octop.messages")
    assert dict(point.attributes) == {}


def test_unknown_counter_is_ignored(reader: InMemoryMetricReader) -> None:
    record_counter("nope")
    assert metric_points(reader, "octop.messages") == []


def test_inc_without_telemetry_only_updates_snapshot() -> None:
    m = Metrics()
    m.inc("cron_runs_total")
    assert m.snapshot()["cron_runs_total"] == 1


def test_inc_survives_telemetry_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(name: str, n: int = 1, **labels: str) -> None:
        raise RuntimeError("exporter exploded")

    monkeypatch.setattr("octop.infra.telemetry.record_counter", boom)
    m = Metrics()
    m.inc("messages_total")
    assert m.snapshot()["messages_total"] == 1


def test_agents_active_gauge(reader: InMemoryMetricReader) -> None:
    bind_active_agents(lambda: 4)
    (point,) = metric_points(reader, "octop.agent.active")
    assert point.value == 4


def test_agents_active_gauge_survives_callback_error(reader: InMemoryMetricReader) -> None:
    def boom() -> int:
        raise ZeroDivisionError

    bind_active_agents(boom)
    assert metric_points(reader, "octop.agent.active") == []
