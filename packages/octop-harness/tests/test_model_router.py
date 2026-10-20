"""Tests for ``octop_harness.middleware.model_router.ModelRouterMiddleware``.

These tests build a synthetic ``ModelRequest`` via direct construction so we
can exercise the priority chain without spinning up the full LangGraph
runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage

from octop_harness.config import HarnessAgentConfig, ModelConfig, ProviderConfig
from octop_harness.llm.factory import ChatModelFactory
from octop_harness.middleware.model_router import ModelRouterMiddleware

# ---------------------------------------------------------------------------
# Test scaffolding
# ---------------------------------------------------------------------------


@dataclass
class FakeRuntime:
    """Minimal stand-in for langgraph's ``Runtime`` carrying a config dict."""

    config: dict[str, Any]


@dataclass
class FakeModelRequest:
    """Light-weight ModelRequest stand-in.

    The middleware only touches ``messages``, ``model``, ``state``, and
    ``runtime`` so we don't need the full LangChain dataclass here.
    """

    messages: list[Any]
    model: Any = None
    state: dict[str, Any] = None  # type: ignore[assignment]
    runtime: FakeRuntime | None = None


@pytest.fixture
def cfg(tmp_path: Any) -> HarnessAgentConfig:
    provider = ProviderConfig(
        id="p",
        base_url="https://x",
        api_key="k",
        models=[
            ModelConfig(id="text", input=["text"]),
            ModelConfig(id="vision", input=["text", "image"]),
            ModelConfig(id="fast", input=["text"]),
        ],
    )
    return HarnessAgentConfig(
        workspace_dir=tmp_path,
        providers=[provider],
        default_model="p/text",
        multimodal_model="p/vision",
    )


@pytest.fixture
def factory_with_sentinels(cfg: HarnessAgentConfig) -> tuple[ChatModelFactory, dict[str, object]]:
    """A factory whose ``get`` returns deterministic sentinel objects."""
    sentinels: dict[str, object] = {
        "p/text": MagicMock(name="text-model"),
        "p/vision": MagicMock(name="vision-model"),
        "p/fast": MagicMock(name="fast-model"),
    }

    factory = ChatModelFactory(cfg.providers)
    # Pre-populate the internal cache so .get() never tries to build a real client.
    factory._cache.update(sentinels)  # type: ignore[attr-defined]
    return factory, sentinels


def _identity_handler(request: Any) -> Any:
    """A minimal handler that simply records the request and returns it."""
    return request


# ---------------------------------------------------------------------------
# Priority chain tests
# ---------------------------------------------------------------------------


class TestPriorityChain:
    def test_explicit_configurable_model_wins(
        self,
        cfg: HarnessAgentConfig,
        factory_with_sentinels: tuple[ChatModelFactory, dict[str, object]],
    ) -> None:
        factory, sentinels = factory_with_sentinels
        mw = ModelRouterMiddleware(cfg, factory)
        req = FakeModelRequest(
            messages=[HumanMessage(content="hi")],
            runtime=FakeRuntime(config={"configurable": {"model": "p/fast"}}),
        )
        mw.wrap_model_call(req, _identity_handler)  # type: ignore[arg-type]
        assert req.model is sentinels["p/fast"]

    def test_user_selector_used_when_no_explicit(
        self,
        cfg: HarnessAgentConfig,
        factory_with_sentinels: tuple[ChatModelFactory, dict[str, object]],
    ) -> None:
        factory, sentinels = factory_with_sentinels
        cfg_with_selector = HarnessAgentConfig(
            workspace_dir=cfg.workspace_dir,
            providers=cfg.providers,
            default_model=cfg.default_model,
            multimodal_model=cfg.multimodal_model,
            model_selector=lambda _state, _config: "p/fast",
        )
        mw = ModelRouterMiddleware(cfg_with_selector, factory)
        req = FakeModelRequest(
            messages=[HumanMessage(content="hi")],
            runtime=FakeRuntime(config={"configurable": {}}),
        )
        mw.wrap_model_call(req, _identity_handler)  # type: ignore[arg-type]
        assert req.model is sentinels["p/fast"]

    def test_user_selector_returning_none_falls_through(
        self,
        cfg: HarnessAgentConfig,
        factory_with_sentinels: tuple[ChatModelFactory, dict[str, object]],
    ) -> None:
        factory, sentinels = factory_with_sentinels
        cfg_with_selector = HarnessAgentConfig(
            workspace_dir=cfg.workspace_dir,
            providers=cfg.providers,
            default_model=cfg.default_model,
            multimodal_model=cfg.multimodal_model,
            model_selector=lambda _s, _c: None,
        )
        mw = ModelRouterMiddleware(cfg_with_selector, factory)
        req = FakeModelRequest(
            messages=[HumanMessage(content="hi")],
            runtime=FakeRuntime(config={"configurable": {}}),
        )
        mw.wrap_model_call(req, _identity_handler)  # type: ignore[arg-type]
        # No multimodal content → default
        assert req.model is sentinels["p/text"]
        assert req.runtime.config["configurable"]["model"] == "p/text"

    def test_multimodal_detection_picks_vision_model(
        self,
        cfg: HarnessAgentConfig,
        factory_with_sentinels: tuple[ChatModelFactory, dict[str, object]],
    ) -> None:
        factory, sentinels = factory_with_sentinels
        mw = ModelRouterMiddleware(cfg, factory)
        req = FakeModelRequest(
            messages=[
                HumanMessage(
                    content=[
                        {"type": "text", "text": "what is this?"},
                        {"type": "image_url", "image_url": "https://..."},
                    ],
                ),
            ],
            runtime=FakeRuntime(config={"configurable": {}}),
        )
        mw.wrap_model_call(req, _identity_handler)  # type: ignore[arg-type]
        assert req.model is sentinels["p/vision"]

    def test_text_only_uses_default(
        self,
        cfg: HarnessAgentConfig,
        factory_with_sentinels: tuple[ChatModelFactory, dict[str, object]],
    ) -> None:
        factory, sentinels = factory_with_sentinels
        mw = ModelRouterMiddleware(cfg, factory)
        req = FakeModelRequest(
            messages=[HumanMessage(content="hi")],
            runtime=FakeRuntime(config={"configurable": {}}),
        )
        mw.wrap_model_call(req, _identity_handler)  # type: ignore[arg-type]
        assert req.model is sentinels["p/text"]

    def test_no_runtime_falls_back_to_default(
        self,
        cfg: HarnessAgentConfig,
        factory_with_sentinels: tuple[ChatModelFactory, dict[str, object]],
    ) -> None:
        factory, sentinels = factory_with_sentinels
        mw = ModelRouterMiddleware(cfg, factory)
        req = FakeModelRequest(messages=[HumanMessage(content="hi")], runtime=None)
        mw.wrap_model_call(req, _identity_handler)  # type: ignore[arg-type]
        assert req.model is sentinels["p/text"]

    def test_multimodal_fallback_when_no_multimodal_configured(
        self,
        tmp_path: Any,
        factory_with_sentinels: tuple[ChatModelFactory, dict[str, object]],
    ) -> None:
        # Provider with only text models.
        provider = ProviderConfig(
            id="p",
            base_url="https://x",
            api_key="k",
            models=[ModelConfig(id="text", input=["text"])],
        )
        cfg_no_mm = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[provider],
            default_model="p/text",
        )
        factory = ChatModelFactory(cfg_no_mm.providers)
        sentinel = MagicMock(name="text-model")
        factory._cache["p/text"] = sentinel
        mw = ModelRouterMiddleware(cfg_no_mm, factory)
        req = FakeModelRequest(
            messages=[
                HumanMessage(content=[{"type": "image_url", "image_url": "x"}]),
            ],
            runtime=FakeRuntime(config={"configurable": {}}),
        )
        mw.wrap_model_call(req, _identity_handler)  # type: ignore[arg-type]
        # No multimodal model available → default.
        assert req.model is sentinel

    def test_user_selector_exception_falls_through(
        self,
        cfg: HarnessAgentConfig,
        factory_with_sentinels: tuple[ChatModelFactory, dict[str, object]],
    ) -> None:
        factory, sentinels = factory_with_sentinels

        def boom(_state: Any, _config: Any) -> str:
            raise RuntimeError("oops")

        cfg_boom = HarnessAgentConfig(
            workspace_dir=cfg.workspace_dir,
            providers=cfg.providers,
            default_model=cfg.default_model,
            multimodal_model=cfg.multimodal_model,
            model_selector=boom,
        )
        mw = ModelRouterMiddleware(cfg_boom, factory)
        req = FakeModelRequest(
            messages=[HumanMessage(content="hi")],
            runtime=FakeRuntime(config={"configurable": {}}),
        )
        mw.wrap_model_call(req, _identity_handler)  # type: ignore[arg-type]
        assert req.model is sentinels["p/text"]

    @pytest.mark.asyncio
    async def test_async_path_mirrors_sync(
        self,
        cfg: HarnessAgentConfig,
        factory_with_sentinels: tuple[ChatModelFactory, dict[str, object]],
    ) -> None:
        factory, sentinels = factory_with_sentinels
        mw = ModelRouterMiddleware(cfg, factory)
        req = FakeModelRequest(
            messages=[HumanMessage(content="hi")],
            runtime=FakeRuntime(config={"configurable": {"model": "p/fast"}}),
        )

        async def async_handler(r: Any) -> Any:
            return r

        await mw.awrap_model_call(req, async_handler)  # type: ignore[arg-type]
        assert req.model is sentinels["p/fast"]
