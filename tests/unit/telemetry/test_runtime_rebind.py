"""DB hot-swap keeps ``gen_ai.agent.name`` resolvable."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from octop.infra.server import AppRuntime
from octop.infra.telemetry import bind_agent_repo, bind_provider_repo, record_inference_usage
from tests.support.otel import active_telemetry, metric_points


class _Repo:
    def __init__(self, name: str) -> None:
        self.name = name

    def get(self, agent_id: str) -> SimpleNamespace:
        return SimpleNamespace(name=self.name)


def test_replace_services_rebinds_agent_name_source() -> None:
    runtime = AppRuntime(
        agent_registry=MagicMock(),
        gateway=MagicMock(),
        cron_manager=MagicMock(),
        user_manager=MagicMock(),
        proactive_scheduler=MagicMock(),
    )
    with active_telemetry() as reader:
        bind_agent_repo(_Repo("old-db"))
        services: Any = SimpleNamespace(
            repos=MagicMock(), agent_repo=_Repo("new-db"), provider_repo=MagicMock()
        )
        runtime.replace_services(services, MagicMock())
        record_inference_usage(
            agent_id="a1",
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
    assert names == {"new-db"}


def test_replace_services_rebinds_provider_source() -> None:
    class _Providers:
        def __init__(self, kind: str) -> None:
            self.kind = kind

        def get_by_name(self, name: str) -> SimpleNamespace:
            return SimpleNamespace(kind=self.kind)

    runtime = AppRuntime(
        agent_registry=MagicMock(),
        gateway=MagicMock(),
        cron_manager=MagicMock(),
        user_manager=MagicMock(),
        proactive_scheduler=MagicMock(),
    )
    with active_telemetry() as reader:
        bind_provider_repo(_Providers("anthropic"))
        services: Any = SimpleNamespace(
            repos=MagicMock(), agent_repo=_Repo("x"), provider_repo=_Providers("openai")
        )
        runtime.replace_services(services, MagicMock())
        record_inference_usage(
            agent_id="a1",
            source="chat",
            provider="p",
            request_model="m",
            response_model="m",
            input_tokens=3,
            output_tokens=1,
        )
        names = {
            p.attributes.get("gen_ai.provider.name")
            for p in metric_points(reader, "gen_ai.client.inference.usage.input_tokens")
        }
    bind_provider_repo(None)
    assert names == {"openai"}
