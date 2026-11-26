"""record_agent_invocation: gen_ai.invoke_agent.duration attributes and isolation."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from octop.infra.telemetry import bind_agent_repo, exception_type, record_agent_invocation
from tests.support.otel import active_telemetry, metric_points

NAME = "gen_ai.invoke_agent.duration"


@pytest.fixture
def reader() -> Iterator[InMemoryMetricReader]:
    with active_telemetry() as r:
        yield r
    bind_agent_repo(None)


def test_success_point(reader: InMemoryMetricReader) -> None:
    bind_agent_repo(SimpleNamespace(get=lambda _id: SimpleNamespace(name="Writer")))
    record_agent_invocation(agent_id="a1", source="chat", duration_s=1.5)
    (point,) = metric_points(reader, NAME)
    assert point.count == 1
    assert point.sum == pytest.approx(1.5)
    attrs = point.attributes
    assert attrs["gen_ai.operation.name"] == "invoke_agent"
    assert attrs["gen_ai.agent.id"] == "a1"
    assert attrs["gen_ai.agent.name"] == "Writer"
    assert attrs["octop.usage.source"] == "chat"
    assert "error.type" not in attrs
    # Octop agents may route across models, so the spec says not to set request.model.
    assert "gen_ai.request.model" not in attrs


def test_failure_point_carries_error_type(reader: InMemoryMetricReader) -> None:
    record_agent_invocation(agent_id="a1", source="cron", duration_s=0.2, error_type="TimeoutError")
    (point,) = metric_points(reader, NAME)
    assert point.attributes["error.type"] == "TimeoutError"


def test_negative_duration_is_dropped(reader: InMemoryMetricReader) -> None:
    record_agent_invocation(agent_id="a1", source="chat", duration_s=-1.0)
    assert metric_points(reader, NAME) == []


def test_inactive_is_a_noop() -> None:
    record_agent_invocation(agent_id="a1", source="chat", duration_s=1.0)


class _Local(Exception):
    pass


def test_exception_type_is_the_canonical_name() -> None:
    assert exception_type(None) == ""
    assert exception_type(TimeoutError()) == "TimeoutError"
    assert exception_type(_Local()) == f"{__name__}._Local"
    import httpx

    assert exception_type(httpx.ConnectError("x")) == "httpx.ConnectError"
