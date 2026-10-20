"""Langfuse tracing via LangChain CallbackHandler."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, replace
from typing import Any

from octop_harness.request import ChatRequest

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LangfuseConfig:
    """Credentials for Langfuse tracing."""

    enabled: bool = False
    public_key: str = ""
    host: str = ""
    secret_key: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.public_key.strip() and self.host.strip() and self.secret_key.strip())


class LangfuseTracer:
    """Langfuse client + graph-level callbacks; per-request trace metadata only."""

    def __init__(self, config: LangfuseConfig | None = None) -> None:
        self._config: LangfuseConfig | None = config if config and config.configured else None
        self._client: Any | None = None
        self._handler: Any | None = None
        self._fingerprint = ""

    def set_config(self, config: LangfuseConfig | None) -> None:
        """Hot-update tracing credentials (e.g. after admin settings change)."""
        active = config if config and config.configured else None
        fp = self._fingerprint_for(active)
        if fp != self._fingerprint:
            self._shutdown_client()
            self._handler = None
        self._config = active
        self._fingerprint = fp

    @property
    def callbacks(self) -> list[Any] | None:
        """CallbackHandler list for ``graph.with_config``; ``None`` when disabled."""
        if self._config is None:
            return None
        if self._handler is None:
            from langfuse.langchain import CallbackHandler

            self._get_client()
            self._handler = CallbackHandler(public_key=self._config.public_key)
        return [self._handler]

    def enrich_request(self, request: ChatRequest) -> ChatRequest:
        """Attach per-invocation Langfuse metadata (session, user, agent)."""
        if self._config is None:
            return request

        metadata = {
            **dict(request.metadata or {}),
            "langfuse_user_id": str(request.user or ""),
            "langfuse_session_id": str(request.thread_id or ""),
            "agent_id": str(request.agent_id or ""),
            "source": str(request.source or "unknown"),
        }
        return replace(request, metadata=metadata)

    def flush(self) -> None:
        client = self._client
        if client is None:
            return
        with contextlib.suppress(Exception):
            client.flush()

    async def flush_async(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.flush)

    def _fingerprint_for(self, config: LangfuseConfig | None) -> str:
        if config is None:
            return ""
        return f"{config.public_key}:{config.host}:{config.secret_key}"

    def _get_client(self) -> Any | None:
        if self._config is None:
            return None
        fp = self._fingerprint_for(self._config)
        if self._client is None or fp != self._fingerprint:
            from langfuse import Langfuse

            self._shutdown_client()
            self._client = Langfuse(
                secret_key=self._config.secret_key,
                public_key=self._config.public_key,
                host=self._config.host.rstrip("/"),
            )
            self._fingerprint = fp
        return self._client

    def _shutdown_client(self) -> None:
        if self._client is not None:
            with contextlib.suppress(Exception):
                self._client.shutdown()
        self._client = None
