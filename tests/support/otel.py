"""OpenTelemetry in-memory helpers for tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from octop.infra.telemetry import init_telemetry, shutdown_telemetry


@contextmanager
def active_telemetry() -> Iterator[InMemoryMetricReader]:
    """Run with telemetry active on an in-memory reader; always reset afterwards."""
    shutdown_telemetry()
    reader = InMemoryMetricReader()
    init_telemetry(environ={}, reader=reader)
    try:
        yield reader
    finally:
        shutdown_telemetry()


def metric_points(reader: InMemoryMetricReader, name: str) -> list[Any]:
    """Return the data points collected for the metric called *name*."""
    data = reader.get_metrics_data()
    if data is None:
        return []
    points: list[Any] = []
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name == name:
                    points.extend(metric.data.data_points)
    return points


def points_by_attr(points: list[Any], key: str) -> dict[object, Any]:
    """Index data points by one attribute value."""
    return {p.attributes.get(key): p for p in points}
