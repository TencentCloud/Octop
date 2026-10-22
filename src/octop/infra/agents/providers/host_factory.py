"""Process-level ``ChatModelFactory`` for one-shot calls outside an agent turn.

Agent startup binds the shared harness factory to whichever agent started
last. This factory is never handed to ``HarnessAgent``, so ``get_for("auto")``
keeps using harness routing over the current provider list.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import cast

from octop_harness.config import HarnessAgentConfig, ProviderConfig
from octop_harness.llm.access import ModelAccess
from octop_harness.llm.factory import ChatModelFactory
from octop_harness.protocols.base import ChatProtocol

from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)


def _host_protocol(_name: str | None) -> ChatProtocol:
    raise RuntimeError("host model calls do not use a chat protocol")


class HostModelFactory:
    """Harness factory whose auto route is the first enabled provider model."""

    def __init__(self) -> None:
        self._factory: ChatModelFactory | None = None
        self._config: HarnessAgentConfig | None = None

    def sync(self, providers: list[ProviderConfig]) -> None:
        """Replace the routed providers. An empty list closes the factory."""
        if not providers:
            self.close()
            return
        if self._factory is None or self._config is None:
            config = HarnessAgentConfig(name="octop-host", providers=list(providers))
            factory = ChatModelFactory(list(providers), agent_config=config)
            factory.bind_runtime(
                get_protocol=cast(
                    "Callable[[str | None], ChatProtocol]",
                    _host_protocol,
                ),
                agent_config=config,
            )
            self._config = config
            self._factory = factory
            return

        self._config.providers = list(providers)
        factory = self._factory
        incoming = {provider.id: provider for provider in providers}
        for provider_id in list(factory._providers):
            if provider_id not in incoming:
                factory._providers.pop(provider_id, None)
                factory.clear_provider_cache(provider_id)
        for provider in providers:
            factory._providers[provider.id] = provider
            factory.clear_provider_cache(provider.id)

    def get(self, spec: str | None) -> ModelAccess:
        """Return ``ModelAccess`` for an explicit ref, or harness ``auto``."""
        factory = self._factory
        if factory is None:
            raise OctopError(ErrorCode.INTERNAL_ERROR, "model factory unavailable")
        requested = (spec or "").strip()
        if not requested or requested.lower() == "auto":
            requested = "auto"
        try:
            return factory.get_for(requested)
        except Exception as exc:
            logger.warning("host model unavailable spec=%s: %s", requested, exc)
            if requested == "auto":
                raise OctopError(
                    ErrorCode.INTERNAL_ERROR,
                    "no usable model for text assist",
                ) from exc
            raise OctopError(
                ErrorCode.INTERNAL_ERROR,
                "model unavailable for text assist",
            ) from exc

    def close(self) -> None:
        factory = self._factory
        self._factory = None
        self._config = None
        if factory is not None:
            factory.close()


__all__ = ["HostModelFactory"]
