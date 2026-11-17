"""Optional decision-model access for inbound plugins."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from octop_harness.decision.client import HttpDecisionClient
from octop_harness.decision.config import DecisionConfig
from octop_harness.plugins.registry import PluginRegistry

from octop.infra.gateway.gateway import Gateway


def test_admission_binding_supports_old_and_new_gateway():
    gateway = Gateway.__new__(Gateway)
    gateway._bind_plugin_inbound(SimpleNamespace())
    manager = SimpleNamespace(set_inbound_handler=Mock())
    gateway._bind_plugin_inbound(manager)
    manager.set_inbound_handler.assert_called_once_with(gateway._plugin_inbound)


@pytest.mark.asyncio
async def test_old_harness_without_admission_keeps_native_routing(monkeypatch):
    monkeypatch.delattr(PluginRegistry, "all_inbound", raising=False)
    gateway = Gateway.__new__(Gateway)
    assert await gateway._plugin_inbound(None, None, None) is False


@pytest.mark.asyncio
async def test_inbound_plugin_uses_current_decision_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Handler:
        provider = None

        def bind_decision_scorer(self, provider):
            self.provider = provider

        async def handle(self, channel, message, dispatch):
            return False

    handler = Handler()
    monkeypatch.setattr(PluginRegistry, "all_inbound", lambda _: [handler], raising=False)
    store = SimpleNamespace(harness_config=lambda: None)
    gateway = Gateway.__new__(Gateway)
    gateway._agent_manager = SimpleNamespace(decision=store)
    assert await gateway._plugin_inbound(None, None, None) is False
    assert await handler.provider() is None

    store.harness_config = lambda: DecisionConfig(
        enabled=True, provider="custom", endpoint="https://example.test"
    )

    async def fake_score(self, **kwargs):
        return {"participate": 0.9}

    monkeypatch.setattr(HttpDecisionClient, "score_async", fake_score)
    scorer = await handler.provider()
    assert await scorer(state="test", statements=[("participate", "test")]) == {"participate": 0.9}
