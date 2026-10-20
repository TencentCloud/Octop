"""Runtime wiring for the structured ``octop-memory`` integration.

``HarnessAgent`` has several memory touchpoints: tools, middleware,
checkpointer reuse, and session-end extraction. This module keeps those
touchpoints behind one small component so the agent facade does not need to
know how ``Memory`` / ``MemoryService`` are assembled.
"""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from octop_memory import Memory, MemoryService

from octop_harness.builtin.tools.memory_tools import build_memory_tools
from octop_harness.memory.llm_client import HarnessAgentLLMClient
from octop_harness.memory.store import (
    MemoryIdentity,
    close_memory_resources,
    memory_identity,
    resolve_backend_config,
    shared_memory_store,
)
from octop_harness.middleware.memory import MemoryMiddleware

if TYPE_CHECKING:
    from octop_harness.backends.workspace import BackendWorkspace
    from octop_harness.config import HarnessAgentConfig
    from octop_harness.llm.factory import ChatModelFactory

logger = logging.getLogger(__name__)


class MemoryRuntime:
    """Per-agent memory wiring: tools, middleware, aux LLM.

    The ``Memory`` backend + checkpointer pool is process-shared for a given
    namespace + DSN/path (see ``octop_harness.memory.store``). Rebuilds swap
    this runtime and the graph; they do not open a second store.
    """

    def __init__(
        self,
        *,
        config: HarnessAgentConfig,
        workspace_path: Path,
        model_factory: ChatModelFactory,
        workspace: BackendWorkspace | None = None,
    ) -> None:
        self._config = config
        self._workspace_path = workspace_path
        self._model_factory = model_factory
        self._memory: Memory | None = None
        self._memory_key: MemoryIdentity | None = None
        self._service: MemoryService | None = None
        self._middleware: MemoryMiddleware | None = None
        self._middleware_kwargs: dict[str, Any] | None = None
        self._llm_client: HarnessAgentLLMClient | None = None

        if config.memory_enabled:
            self._memory = self._build_memory()
            self._llm_client = self._build_llm_client() if config.memory_aux_model_enabled else None
            self._service = MemoryService(
                self._memory,
                llm=self._llm_client,
                config=_extraction_service_config(config),
                host="octop-harness",
                manual_documents_provider=(
                    lambda: {
                        name: (workspace.download_bytes(name) or b"").decode("utf-8")
                        for name in ("USER.md", "MEMORY.md")
                    }
                )
                if workspace is not None
                else None,
            )

    @property
    def memory(self) -> Any | None:
        """The backing ``Memory`` instance, or ``None`` when disabled."""
        return self._memory

    @property
    def service(self) -> Any | None:
        """The bound ``MemoryService``, or ``None`` when memory is disabled."""
        return self._service

    @property
    def middleware(self) -> MemoryMiddleware | None:
        """The cached middleware instance, once built for the graph."""
        return self._middleware

    def build_tools(self) -> list[Any]:
        """Return service-backed memory tools for the agent tool list."""
        if self._service is None:
            return []
        return list(build_memory_tools(self._service))

    def build_middleware(self) -> MemoryMiddleware | None:
        """Build ``MemoryMiddleware`` for memory capture and/or JSONL.

        ``MemoryMiddleware`` handles two concerns: the MemoryService lifecycle
        hooks and the daily JSONL session log. They can be toggled
        independently:

        * ``memory_enabled=False`` (or no service) -> JSONL only.
        * ``session_log_enabled=False`` -> MemoryService only.
        * Both off -> middleware skipped entirely (return ``None``).

        When Memory is on, JSONL additionally honors ``memory_jsonl_enabled``;
        when Memory is off, only ``session_log_enabled`` gates JSONL.
        """
        cfg = self._config
        service = self._service
        if service is None and not cfg.session_log_enabled:
            return None

        jsonl_active = cfg.session_log_enabled and (service is None or cfg.memory_jsonl_enabled)
        jsonl_dir_cfg = cfg.memory_jsonl_dir if cfg.memory_jsonl_dir is not None else cfg.session_log_dir
        if jsonl_dir_cfg is None:
            prefix = str(cfg.system_files_path or "").strip()
            system = self._workspace_path / prefix if prefix else self._workspace_path
            jsonl_dir = system / "sessions"
        else:
            jsonl_dir = Path(jsonl_dir_cfg)
            if not jsonl_dir.is_absolute():
                jsonl_dir = self._workspace_path / jsonl_dir

        # Mutually exclusive automatic triggers: wire exactly one timer.
        extract_idle_seconds = 0.0
        extract_interval_seconds = 0.0
        if cfg.memory_extract_on_session_end:
            if cfg.memory_extract_trigger_mode == "interval":
                extract_interval_seconds = cfg.memory_extract_interval_seconds
            else:
                extract_idle_seconds = cfg.memory_extract_idle_seconds
        on_chat_model = self._llm_client.set_current_model if self._llm_client is not None else None
        # Slimming is host-scheduled (ADR-027). Default on when MemoryService
        # is bound; one-shot MemoryMiddleware() elsewhere stays off (0).
        maintenance_interval = 3600.0 if service is not None else 0.0
        kwargs: dict[str, Any] = {
            "service": service,
            "recall_inject_enabled": cfg.memory_recall_inject_enabled,
            "capture_enabled": cfg.memory_capture_enabled,
            "extract_idle_seconds": extract_idle_seconds,
            "extract_interval_seconds": extract_interval_seconds,
            "jsonl_enabled": jsonl_active,
            "jsonl_dir": jsonl_dir if jsonl_active else None,
            "jsonl_max_bytes": cfg.session_log_max_bytes,
            "on_chat_model": on_chat_model,
            "maintenance_interval_seconds": maintenance_interval,
            # Start the first cheap GC + incremental-vacuum pass shortly after
            # binding. Full compact/VACUUM remains an explicit operator action.
            "maintenance_initial_delay_seconds": 1.0,
        }
        # The middleware owns live timers (maintenance, interval/idle extract)
        # and per-session state; none of it depends on the graph shape. A
        # recompile (MCP tool injection, subagent reload, bootstrap) must
        # therefore reuse the running instance: building a second one would
        # arm a duplicate hourly timer, and the dropped instance is kept alive
        # by its own ``threading.Timer`` — it re-arms forever, so every
        # recompile used to leak one more maintenance beat.
        previous = self._middleware
        if previous is not None and self._middleware_kwargs == kwargs:
            return previous
        self._middleware = MemoryMiddleware(**kwargs)
        self._middleware_kwargs = kwargs
        if previous is not None:
            # Config actually changed — retire the old timers rather than
            # letting them run beside the new ones.
            with contextlib.suppress(Exception):
                previous.shutdown()
        return self._middleware

    def end_session(
        self,
        session_id: str,
        *,
        background: bool = True,
    ) -> None:
        """Trigger MemoryService extraction for a finished logical session."""
        if not self._config.memory_extract_on_session_end:
            return
        if self._service is None:
            return
        middleware = self._middleware
        if middleware is None:
            middleware = MemoryMiddleware(service=self._service, jsonl_enabled=False)
        middleware.end_session(session_id, background=background)

    def close(self) -> None:
        """Drop this runtime's claim on ``Memory`` (idempotent).

        Middleware / aux LLM are always torn down — they are per-agent.
        The shared ``Memory`` (backend + checkpointer pool) is released to
        the process store and only closed when the last runtime lets go.
        """
        middleware = self._middleware
        if middleware is not None:
            with contextlib.suppress(Exception):
                middleware.shutdown()
        key = self._memory_key
        memory = self._memory
        self._memory_key = None
        self._memory = None
        self._service = None
        self._middleware = None
        self._middleware_kwargs = None
        self._llm_client = None
        if key is not None:
            shared_memory_store().release(key)
            return
        if memory is not None:
            close_memory_resources(memory)

    def __del__(self) -> None:
        with contextlib.suppress(Exception):  # pragma: no cover - destructor must not raise
            self.close()

    def _build_memory(self) -> Memory:
        """Acquire the backing ``Memory``, sharing one per namespace + location.

        ``memory_backend`` may be a backend-type string, a dict spec
        (``{"type": "...", **kwargs}``), or a pre-built ``MemoryBackend``.
        SQLite defaults to a per-agent ``{workspace}/memory.sqlite``.
        Live backend instances are not shared.
        """
        identity = memory_identity(self._config, self._workspace_path)
        if identity is None:
            return self._construct_memory()
        self._memory_key = identity
        return shared_memory_store().acquire(identity, self._construct_memory)

    def _construct_memory(self) -> Memory:
        cfg = self._config
        spec = cfg.memory_backend
        namespace = cfg.memory_namespace or cfg.name

        if isinstance(spec, str):
            return Memory(
                namespace=namespace,
                backend=spec,
                backend_config=self._memory_backend_config(spec, cfg.memory_backend_config),
            )
        if isinstance(spec, dict):
            backend_type = spec.get("type", "sqlite")
            backend_config = {str(k): v for k, v in spec.items() if k != "type"}
            resolved_config = self._memory_backend_config(str(backend_type), backend_config)
            return Memory(namespace=namespace, backend=backend_type, backend_config=resolved_config)
        return Memory(namespace=namespace, backend=spec)

    def _memory_backend_config(
        self,
        backend_type: str,
        config: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Apply workspace-scoped defaults to the memory backend config."""
        return resolve_backend_config(self._config, self._workspace_path, backend_type, config)

    def _build_llm_client(self) -> HarnessAgentLLMClient | None:
        """Build the auxiliary LLM client used by extraction / promotion."""
        cfg = self._config
        aux = cfg.memory_aux_light_model or cfg.memory_aux_heavy_model
        default = cfg.default_model
        if aux is None and default is None:
            logger.info("memory aux LLM disabled: no aux / default model ref configured")
            return None
        try:
            return HarnessAgentLLMClient(
                self._model_factory,
                aux_model=aux,
                default_model=default,
                light_timeout_s=cfg.memory_aux_light_timeout_s,
                heavy_timeout_s=cfg.memory_aux_heavy_timeout_s,
                default_max_tokens=cfg.memory_aux_max_tokens,
                extra_body=cfg.memory_aux_extra_body,
                thinking=cfg.memory_aux_thinking,
                max_retries=cfg.memory_aux_max_retries,
                retry_backoff_s=cfg.memory_aux_retry_backoff_s,
            )
        except (ValueError, TypeError):  # pragma: no cover - defensive
            logger.warning(
                "memory aux LLM client construction failed; extraction will degrade",
                exc_info=True,
            )
            return None


def _extraction_service_config(config: HarnessAgentConfig) -> dict[str, Any] | None:
    """Budget passed into octop-memory's extractor.

    ``CandidateExtractor`` always sends its own ``max_tokens`` (default
    2048). A harness-side fallback on the chat client never overrides that,
    so the host budget has to land in ``extraction.max_tokens``.
    """
    if config.memory_extract_max_tokens is None:
        return None
    return {"extraction": {"max_tokens": config.memory_extract_max_tokens}}


__all__ = ["MemoryRuntime"]
