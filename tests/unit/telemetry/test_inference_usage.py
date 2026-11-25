"""record_inference_usage: gen_ai.client.inference.* instruments and attributes."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from octop.infra.telemetry import (
    bind_agent_repo,
    bind_provider_repo,
    record_inference_usage,
    shutdown_telemetry,
)
from tests.support.otel import active_telemetry, metric_points

USAGE_IN = "gen_ai.client.inference.usage.input_tokens"
USAGE_OUT = "gen_ai.client.inference.usage.output_tokens"
USAGE_CACHE_READ = "gen_ai.client.inference.usage.cache_read.input_tokens"
USAGE_CACHE_WRITE = "gen_ai.client.inference.usage.cache_write.input_tokens"
USAGE_REASONING = "gen_ai.client.inference.usage.reasoning.output_tokens"
OP_IN = "gen_ai.client.inference.operation.input_tokens"
OP_OUT = "gen_ai.client.inference.operation.output_tokens"


class _AgentRepo:
    def __init__(self, names: dict[str, str] | None = None, *, fail: bool = False) -> None:
        self.names = names or {}
        self.fail = fail

    def get(self, agent_id: str) -> SimpleNamespace | None:
        if self.fail:
            raise RuntimeError("db down")
        name = self.names.get(agent_id)
        return None if name is None else SimpleNamespace(name=name)


class _ProviderRepo:
    def __init__(self, kinds: dict[str, str], *, fail: bool = False) -> None:
        self.kinds = kinds
        self.fail = fail

    def get_by_name(self, name: str) -> SimpleNamespace | None:
        if self.fail:
            raise RuntimeError("db down")
        kind = self.kinds.get(name)
        return None if kind is None else SimpleNamespace(kind=kind)


@pytest.fixture
def reader() -> Iterator[InMemoryMetricReader]:
    with active_telemetry() as r:
        yield r
    bind_agent_repo(None)
    bind_provider_repo(None)


def _record(**overrides: Any) -> None:
    kwargs: dict[str, Any] = {
        "agent_id": "a1",
        "source": "chat",
        "provider": "",
        "request_model": "",
        "response_model": "",
        "input_tokens": 100,
        "output_tokens": 20,
    }
    kwargs.update(overrides)
    record_inference_usage(**kwargs)


def test_counters_carry_required_attributes(reader: InMemoryMetricReader) -> None:
    bind_provider_repo(_ProviderRepo({"janus": "openai"}))
    _record(provider="janus", request_model="m", response_model="m-001")
    (inp,) = metric_points(reader, USAGE_IN)
    (out,) = metric_points(reader, USAGE_OUT)
    assert inp.value == 100
    assert out.value == 20
    attrs = inp.attributes
    assert attrs["gen_ai.operation.name"] == "chat"
    assert attrs["gen_ai.provider.name"] == "openai"
    assert attrs["gen_ai.token.modality"] == "unknown"
    assert attrs["gen_ai.request.model"] == "m"
    assert attrs["gen_ai.response.model"] == "m-001"
    assert attrs["gen_ai.agent.id"] == "a1"
    assert attrs["octop.usage.source"] == "chat"


def test_per_operation_histograms_have_no_modality(reader: InMemoryMetricReader) -> None:
    _record(request_model="m")
    (inp,) = metric_points(reader, OP_IN)
    (out,) = metric_points(reader, OP_OUT)
    assert (inp.count, inp.sum) == (1, 100)
    assert (out.count, out.sum) == (1, 20)
    assert "gen_ai.token.modality" not in inp.attributes
    assert inp.attributes["gen_ai.request.model"] == "m"


def test_each_model_call_is_its_own_histogram_observation(reader: InMemoryMetricReader) -> None:
    _record(input_tokens=10, output_tokens=1)
    _record(input_tokens=30, output_tokens=3)
    (inp,) = metric_points(reader, OP_IN)
    assert (inp.count, inp.sum) == (2, 40)


def test_cache_and_reasoning_counters(reader: InMemoryMetricReader) -> None:
    _record(cache_read_tokens=50, cache_write_tokens=5, reasoning_tokens=7, source="cron")
    (read,) = metric_points(reader, USAGE_CACHE_READ)
    (write,) = metric_points(reader, USAGE_CACHE_WRITE)
    (reasoning,) = metric_points(reader, USAGE_REASONING)
    assert (read.value, write.value, reasoning.value) == (50, 5, 7)
    assert read.attributes["gen_ai.token.modality"] == "unknown"
    assert "gen_ai.token.modality" not in reasoning.attributes
    assert read.attributes["octop.usage.source"] == "cron"


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("openai", "openai"),
        ("anthropic", "anthropic"),
        ("ollama", "ollama"),
        ("azure", "azure.ai.openai"),
        ("gemini", "gcp.gemini"),
        ("mystery", "janus"),
    ],
)
def test_provider_name_maps_kind_to_well_known_value(
    reader: InMemoryMetricReader, kind: str, expected: str
) -> None:
    bind_provider_repo(_ProviderRepo({"janus": kind}))
    _record(provider="janus")
    (inp,) = metric_points(reader, USAGE_IN)
    assert inp.attributes["gen_ai.provider.name"] == expected


def test_provider_falls_back_to_configured_name_when_lookup_fails(
    reader: InMemoryMetricReader,
) -> None:
    bind_provider_repo(_ProviderRepo({}, fail=True))
    _record(provider="janus")
    (inp,) = metric_points(reader, USAGE_IN)
    assert inp.attributes["gen_ai.provider.name"] == "janus"


def test_provider_omitted_when_unknown(reader: InMemoryMetricReader) -> None:
    _record(provider="")
    (inp,) = metric_points(reader, USAGE_IN)
    assert "gen_ai.provider.name" not in inp.attributes


def test_empty_models_omit_attributes(reader: InMemoryMetricReader) -> None:
    _record()
    (inp,) = metric_points(reader, USAGE_IN)
    assert "gen_ai.request.model" not in inp.attributes
    assert "gen_ai.response.model" not in inp.attributes


def test_agent_name_attribute_from_bound_repo(reader: InMemoryMetricReader) -> None:
    bind_agent_repo(_AgentRepo({"a1": "Writer"}))
    _record()
    (inp,) = metric_points(reader, USAGE_IN)
    assert inp.attributes["gen_ai.agent.name"] == "Writer"


def test_agent_name_omitted_when_lookup_fails(reader: InMemoryMetricReader) -> None:
    bind_agent_repo(_AgentRepo(fail=True))
    _record()
    (inp,) = metric_points(reader, USAGE_IN)
    assert "gen_ai.agent.name" not in inp.attributes


def test_agent_name_omitted_for_unknown_agent(reader: InMemoryMetricReader) -> None:
    bind_agent_repo(_AgentRepo({}))
    _record(agent_id="ghost")
    (inp,) = metric_points(reader, USAGE_IN)
    assert "gen_ai.agent.name" not in inp.attributes
    assert inp.attributes["gen_ai.agent.id"] == "ghost"


def test_zero_and_negative_counts_do_not_touch_counters(reader: InMemoryMetricReader) -> None:
    _record(
        input_tokens=0,
        output_tokens=-1,
        cache_read_tokens=-3,
        cache_write_tokens=0,
        reasoning_tokens=0,
    )
    for name in (USAGE_IN, USAGE_OUT, USAGE_CACHE_READ, USAGE_CACHE_WRITE, USAGE_REASONING):
        assert metric_points(reader, name) == []
    # A call that reported zero input is still a (zero-valued) operation observation.
    (inp,) = metric_points(reader, OP_IN)
    assert (inp.count, inp.sum) == (1, 0)
    assert metric_points(reader, OP_OUT) == []


@pytest.mark.parametrize("bad", ["12", 3.5, None, True, float("nan"), [7]])
def test_non_int_token_counts_record_nothing(reader: InMemoryMetricReader, bad: object) -> None:
    _record(
        input_tokens=bad,
        output_tokens=bad,
        cache_read_tokens=bad,
        cache_write_tokens=bad,
        reasoning_tokens=bad,
    )
    for name in (
        USAGE_IN,
        USAGE_OUT,
        USAGE_CACHE_READ,
        USAGE_CACHE_WRITE,
        USAGE_REASONING,
        OP_IN,
        OP_OUT,
    ):
        assert metric_points(reader, name) == []


def test_inactive_is_noop() -> None:
    shutdown_telemetry()
    _record()
