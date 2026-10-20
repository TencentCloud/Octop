"""Build a ``BaseChatModel`` from a ``ProviderConfig`` + ``ModelConfig`` pair.

Per design doc §3.3:
    - ``protocol="openai"``    → ``ChatOpenAI`` (also covers OpenAI-compatible
      vendors via ``base_url``).
    - ``protocol="anthropic"`` → ``ChatAnthropic``.
    - ``protocol="bedrock"``   → ``ChatBedrockConverse`` (optional dependency).

Instances are cached so that we only construct each ``(provider, model_id)``
combination once per agent. The cache key is provider-key-aware so two
``ProviderConfig`` objects sharing a base_url do not collide.

Reasoning-mode ``reasoning_content`` round-trip
-----------------------------------------------
``langchain-openai`` 1.x explicitly drops the non-standard ``reasoning_content``
field that providers like DeepSeek emit on assistant messages (see the
``ChatOpenAI`` docstring upstream). DeepSeek's "thinking" models then 400 on
the next request with::

    The `reasoning_content` in the thinking mode must be passed back to the API.

We solve that with a small ``ChatOpenAI`` subclass that captures
``reasoning_content`` into ``AIMessage.additional_kwargs`` on parse and
re-attaches it on serialize. The behaviour is no-op for providers that don't
emit the field, so it's always-on for ``protocol="openai"``.
"""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import AsyncIterator, Callable, Iterator, Mapping, Sequence
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from octop_harness.config import ModelConfig, ProviderConfig
from octop_harness.llm.session_header import (
    aclose_session_http_clients,
    attach_session_http_clients,
    bind_anthropic_session_header,
    close_session_http_clients,
    session_http_clients,
)
from octop_harness.middleware.turn_model import resolve_turn_model_ref

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from octop_harness.config import HarnessAgentConfig
    from octop_harness.llm.access import ModelAccess
    from octop_harness.protocols.base import ChatProtocol


logger = logging.getLogger(__name__)


class ChatModelFactory:
    """Lazily builds and caches ``BaseChatModel`` instances.

    Designed to be held as a single instance on ``HarnessAgent`` (or shared
    across agents via ``AgentManager``) so that ``ModelRouterMiddleware`` can
    request models by ref ``"<provider_id>/<model_id>"`` without paying
    construction cost on every model call.

    Args:
        providers: List of :class:`~octop_harness.config.ProviderConfig`
            instances. Each provider's ``id`` is used as the lookup key for
            model refs of the form ``"<provider_id>/<model_id>"``.
    """

    def __init__(
        self,
        providers: list[ProviderConfig],
        *,
        agent_config: HarnessAgentConfig | None = None,
        get_protocol: Callable[[str | None], ChatProtocol] | None = None,
    ) -> None:
        # Build id→ProviderConfig index for O(1) lookups in get().
        self._providers: dict[str, ProviderConfig] = {p.id: p for p in providers}
        self._cache: dict[str | tuple[str, int], BaseChatModel] = {}
        self._agent_config = agent_config
        self._get_protocol = get_protocol

    def bind_runtime(
        self,
        *,
        get_protocol: Callable[[str | None], ChatProtocol],
        agent_config: HarnessAgentConfig | None = None,
    ) -> None:
        """Attach graph protocol access after :class:`HarnessAgent` compiles."""
        self._get_protocol = get_protocol
        if agent_config is not None:
            self._agent_config = agent_config

    def provider_configs(self) -> list[ProviderConfig]:
        """Snapshot of provider configs backing this factory (for config sync)."""
        return list(self._providers.values())

    def resolve_ref(
        self,
        spec: Any,
        *,
        messages: Sequence[Any] | None = None,
        configurable: Mapping[str, Any] | None = None,
    ) -> str:
        """Resolve a model spec to ``provider/model`` ref."""
        if isinstance(spec, str):
            stripped = spec.strip()
            if not stripped:
                raise ValueError("model spec must not be empty")
            lower = stripped.lower()
            if lower == "auto":
                return self.resolve_for_turn(
                    configurable=dict(configurable or {}),
                    messages=list(messages or []),
                )
            if "/" in stripped:
                return stripped
            bindings = (self._agent_config.role_bindings or {}) if self._agent_config else {}
            bound = bindings.get(stripped)
            if bound:
                return bound.strip()
            if self._agent_config is not None:
                return self._agent_config.pick_default_model_ref()
            raise ValueError(f"unknown model role {stripped!r} and no agent config for fallback")
        raise ValueError(f"unsupported model spec: {spec!r}")

    def resolve_for_turn(
        self,
        *,
        pick_default_ref: Callable[[], str] | None = None,
        pick_multimodal_ref: Callable[[], str | None] | None = None,
        configurable: Mapping[str, Any] | None = None,
        messages: Sequence[Any] | None = None,
        user_selector: Any = None,
        state: Any = None,
        runtime_config: Mapping[str, Any] | None = None,
    ) -> str:
        cfg = self._agent_config
        return resolve_turn_model_ref(
            pick_default_ref=pick_default_ref or (cfg.pick_default_model_ref if cfg is not None else lambda: ""),
            pick_multimodal_ref=pick_multimodal_ref or (cfg.pick_multimodal_model_ref if cfg is not None else None),
            configurable=configurable,
            messages=messages,
            user_selector=user_selector,
            state=state,
            runtime_config=runtime_config,
        )

    def list_refs(self, *, enabled_only: bool = True) -> list[str]:
        refs: list[str] = []
        for provider in self._providers.values():
            for model in provider.models:
                if enabled_only and not model.enabled:
                    continue
                refs.append(f"{provider.id}/{model.id}")
        return refs

    def get(
        self,
        model_ref: str,
        *,
        get_protocol: Callable[[str | None], ChatProtocol] | None = None,
    ) -> ModelAccess:
        """Return a :class:`ModelAccess` handle for ``provider/model``."""
        from octop_harness.llm.access import ModelAccess

        proto = get_protocol or self._get_protocol
        if proto is None:
            raise RuntimeError(
                "ChatModelFactory.get requires get_protocol=... or prior bind_runtime()",
            )
        return ModelAccess(
            model_ref=model_ref,
            chat_model=self.get_chat_model(model_ref),
            get_protocol=proto,
        )

    def get_for(
        self,
        spec: Any,
        *,
        messages: Sequence[Any] | None = None,
        configurable: Mapping[str, Any] | None = None,
        get_protocol: Callable[[str | None], ChatProtocol] | None = None,
        **kwargs: Any,
    ) -> ModelAccess:
        ref = self.resolve_ref(spec, messages=messages, configurable=configurable)
        return self.get(ref, get_protocol=get_protocol)

    def get_chat_model(self, model_ref: str, *, max_retries: int | None = None) -> BaseChatModel:
        """Return a cached model, optionally with an isolated SDK retry policy.

        Memory uses ``max_retries=0`` and owns retries itself. These instances
        never replace or mutate the model used by the main conversation.
        """
        if max_retries is not None and (
            isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0
        ):
            raise ValueError("max_retries must be a non-negative integer or None")
        cache_key = model_ref if max_retries is None else (model_ref, max_retries)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        provider_key, _, model_id = model_ref.partition("/")
        provider = self._providers.get(provider_key)
        if provider is None:
            raise ValueError(f"Unknown provider {provider_key!r} in model ref {model_ref!r}")
        model = provider.get_model(model_id)
        if model is None or not model.enabled:
            raise ValueError(f"Model {model_ref!r} not found or disabled")
        instance = self._build(provider, model, max_retries=max_retries)
        self._cache[cache_key] = instance
        return instance

    def pop_cached(self, model_ref: str) -> None:
        """Drop a cached model and close any dedicated session-header clients."""
        for key in list(self._cache):
            if key == model_ref or (isinstance(key, tuple) and key[0] == model_ref):
                close_session_http_clients(self._cache.pop(key))

    def clear_provider_cache(self, provider_id: str) -> None:
        """Evict all models for a provider, including isolated retry variants."""
        refs = {key[0] if isinstance(key, tuple) else key for key in self._cache}
        for ref in refs:
            if ref.startswith(f"{provider_id}/"):
                self.pop_cached(ref)

    def close(self) -> None:
        """Close dedicated session-header clients and drop the model cache."""
        for instance in list(self._cache.values()):
            close_session_http_clients(instance)
        self._cache.clear()

    async def aclose(self) -> None:
        """Async variant of :meth:`close`."""
        for instance in list(self._cache.values()):
            await aclose_session_http_clients(instance)
        self._cache.clear()

    # ------------------------------------------------------------------
    # Construction by protocol
    # ------------------------------------------------------------------

    def _build(self, provider: ProviderConfig, model: ModelConfig, *, max_retries: int | None = None) -> BaseChatModel:
        if provider.protocol == "openai":
            return _build_openai(provider, model, max_retries=max_retries)
        if provider.protocol == "anthropic":
            return _build_anthropic(provider, model, max_retries=max_retries)
        if provider.protocol == "bedrock":
            return _build_bedrock(provider, model, max_retries=max_retries)
        raise ValueError(f"Unsupported provider protocol: {provider.protocol!r}")


def build_chat_model(provider: ProviderConfig, model: ModelConfig) -> BaseChatModel:
    """Module-level convenience wrapper (mostly for tests)."""
    if provider.protocol == "openai":
        return _build_openai(provider, model)
    if provider.protocol == "anthropic":
        return _build_anthropic(provider, model)
    if provider.protocol == "bedrock":
        return _build_bedrock(provider, model)
    raise ValueError(f"Unsupported provider protocol: {provider.protocol!r}")


# ---------------------------------------------------------------------------
# Per-protocol builders (each isolates its own optional import)
# ---------------------------------------------------------------------------


def _is_codex_base_url(base_url: str | None) -> bool:
    """Match the ChatGPT Codex endpoint, without affecting API-key providers."""
    endpoint = urlsplit(base_url or "")
    return (
        endpoint.scheme == "https"
        and endpoint.hostname == "chatgpt.com"
        and endpoint.path.rstrip("/") == "/backend-api/codex"
    )


def _build_openai(provider: ProviderConfig, model: ModelConfig, *, max_retries: int | None = None) -> BaseChatModel:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:  # pragma: no cover - covered by install path
        raise ImportError(
            "langchain-openai is required for OpenAI-compatible providers. Install with: pip install langchain-openai",
        ) from exc

    cls = _get_reasoning_aware_chat_openai(ChatOpenAI)

    kwargs: dict[str, Any] = {
        "model": model.id,
        "base_url": provider.base_url,
        "api_key": provider.api_key,
        # langchain-openai only defaults stream_usage on for the official
        # OpenAI endpoint; with a custom base_url (always our case) it stays
        # off and streamed AIMessages carry no usage_metadata.
        "stream_usage": provider.stream_usage,
    }
    if max_retries is not None:
        kwargs["max_retries"] = max_retries
    is_codex = _is_codex_base_url(provider.base_url)
    use_responses_api = is_codex or model.api_mode == "responses"
    if model.native_tool_search and not use_responses_api:
        raise ValueError("OpenAI native_tool_search requires api_mode='responses'")
    kwargs["use_responses_api"] = use_responses_api
    if use_responses_api:
        kwargs["output_version"] = "responses/v1"
    if is_codex:
        # ChatGPT plan tokens require stateless, streaming Responses requests.
        # Keep the complete history, including encrypted reasoning for replay.
        kwargs.update(
            use_responses_api=True,
            store=False,
            streaming=True,
            use_previous_response_id=False,
            output_version="responses/v1",
            include=["reasoning.encrypted_content"],
        )
    if provider.headers:
        kwargs["default_headers"] = dict(provider.headers)
    session_clients = None
    if provider.session_header:
        # Dedicated clients so the hook is not installed on langchain's shared
        # default httpx client (which other providers reuse).
        session_clients = session_http_clients(provider.session_header)
        kwargs["http_client"], kwargs["http_async_client"] = session_clients
    instance: BaseChatModel = cls(**kwargs)
    instance._harness_codex = is_codex  # type: ignore[attr-defined]

    fallback_instance: BaseChatModel | None = None
    # Codex is Responses-only; never retry it through Chat Completions.
    if model.api_fallback == "chat_completions" and not is_codex:
        fallback_kwargs = dict(kwargs)
        fallback_kwargs["use_responses_api"] = False
        fallback_kwargs.pop("output_version", None)
        fallback_instance = cls(**fallback_kwargs)
        object.__setattr__(instance, "_harness_api_fallback_model", fallback_instance)
        object.__setattr__(instance, "_harness_api_fallback_provider", provider.id)
        object.__setattr__(instance, "_harness_api_fallback_model_id", model.id)
    if session_clients is not None:
        attach_session_http_clients(instance, session_clients[0], session_clients[1])
    # Attach supported input modalities so the subclass can strip
    # unsupported content types (e.g. image_url for text-only models).
    instance._harness_supported_input = set(model.input)  # type: ignore[attr-defined]
    if fallback_instance is not None:
        fallback_instance._harness_supported_input = set(model.input)  # type: ignore[attr-defined]
    _stamp_native_tool_search_capability(instance, provider.protocol, model.native_tool_search)
    _inject_model_token_limits(instance, model)
    return instance


# ---------------------------------------------------------------------------
# reasoning_content round-trip subclass
# ---------------------------------------------------------------------------

# Built lazily on first use so importing octop_harness.llm.factory does not
# pay the ``langchain_openai`` import cost when only Anthropic/Bedrock are used.
# Keyed on the base class identity so test patches that swap ``ChatOpenAI`` for
# a mock don't poison the cache for subsequent real-class lookups.
_REASONING_AWARE_CHAT_OPENAI: dict[int, type[Any]] = {}

_RESPONSES_UNSUPPORTED_400_MARKERS: tuple[str, ...] = (
    "responses api is not supported",
    "response api is not supported",
    "does not support responses",
    "doesn't support responses",
    "not support responses",
    "unsupported responses",
    "unsupported endpoint",
    "unknown endpoint",
    "unsupported api mode",
)
_RESPONSES_ONLY_REQUEST_KEYS: frozenset[str] = frozenset(
    {
        "background",
        "context_management",
        "conversation",
        "include",
        "max_tool_calls",
        "previous_response_id",
        "prompt",
        "reasoning",
        "text",
        "truncation",
    }
)


def _is_responses_api_unsupported_error(exc: BaseException) -> bool:
    """Return whether an error clearly means the Responses API is unavailable."""
    status_code = getattr(exc, "status_code", None)
    if status_code in (404, 405, 501):
        return True
    if status_code != 400:
        return False
    body = getattr(exc, "body", None)
    try:
        body_text = json.dumps(body, ensure_ascii=False) if body is not None else ""
    except (TypeError, ValueError):
        body_text = str(body)
    error_text = f"{exc} {body_text}".lower()
    return any(marker in error_text for marker in _RESPONSES_UNSUPPORTED_400_MARKERS)


def _request_allows_chat_completions_fallback(kwargs: Mapping[str, Any]) -> bool:
    if _RESPONSES_ONLY_REQUEST_KEYS.intersection(kwargs):
        return False
    tools = kwargs.get("tools")
    if not isinstance(tools, list):
        return True
    return all(not isinstance(tool, dict) or tool.get("type", "function") == "function" for tool in tools)


def _mark_api_fallback_message(message: Any) -> None:
    metadata = getattr(message, "response_metadata", None)
    if isinstance(metadata, dict):
        metadata["api_fallback"] = "chat_completions"
        metadata["api_mode"] = "chat_completions"


def _mark_api_fallback_result(result: Any) -> Any:
    for generation in getattr(result, "generations", ()):
        _mark_api_fallback_message(getattr(generation, "message", None))
    return result


def _mark_api_fallback_chunk(chunk: Any) -> Any:
    _mark_api_fallback_message(getattr(chunk, "message", None))
    return chunk


def _fallback_model_for(instance: Any, exc: BaseException, kwargs: Mapping[str, Any]) -> Any | None:
    fallback = getattr(instance, "_harness_api_fallback_model", None)
    if fallback is None or not _request_allows_chat_completions_fallback(kwargs):
        return None
    if not _is_responses_api_unsupported_error(exc):
        return None
    logger.warning(
        "Responses API unsupported for provider=%s model=%s; retrying with Chat Completions",
        getattr(instance, "_harness_api_fallback_provider", "?"),
        getattr(instance, "_harness_api_fallback_model_id", "?"),
    )
    return fallback


def _copy_reasoning_from_response(result: Any, response: Any) -> Any:
    from langchain_core.messages import AIMessage

    if isinstance(response, dict):
        choices = response.get("choices") or []
        for gen, choice in zip(result.generations, choices, strict=False):
            msg_dict = choice.get("message") if isinstance(choice, dict) else None
            if not isinstance(msg_dict, dict):
                continue
            reasoning = msg_dict.get("reasoning_content")
            message = getattr(gen, "message", None)
            if reasoning and isinstance(message, AIMessage):
                message.additional_kwargs.setdefault("reasoning_content", reasoning)
        return result
    raw_choices = getattr(response, "choices", None) or []
    for gen, choice in zip(result.generations, raw_choices, strict=False):
        msg = getattr(choice, "message", None)
        if msg is None:
            continue
        reasoning = getattr(msg, "reasoning_content", None)
        if reasoning is None:
            extras = getattr(msg, "model_extra", None) or {}
            reasoning = extras.get("reasoning_content")
        message = getattr(gen, "message", None)
        if reasoning and isinstance(message, AIMessage):
            message.additional_kwargs.setdefault("reasoning_content", reasoning)
    return result


def _copy_reasoning_from_chunk(gen_chunk: Any, chunk: dict[str, Any]) -> Any:
    from langchain_core.messages import AIMessageChunk

    if gen_chunk is None:
        return None
    choices = chunk.get("choices") or chunk.get("chunk", {}).get("choices") or []
    if not choices:
        return gen_chunk
    delta = choices[0].get("delta") if isinstance(choices[0], dict) else None
    if not isinstance(delta, dict):
        return gen_chunk
    reasoning = delta.get("reasoning_content")
    message = getattr(gen_chunk, "message", None)
    if reasoning and isinstance(message, AIMessageChunk):
        message.additional_kwargs.setdefault("reasoning_content", "")
        message.additional_kwargs["reasoning_content"] += reasoning
    return gen_chunk


def _source_messages_for_payload(input_: Any, kwargs: dict[str, Any], convert_input: Any) -> list[Any]:
    from langchain_core.messages import BaseMessage

    if isinstance(input_, list) and all(isinstance(msg, BaseMessage) for msg in input_):
        return input_
    try:
        messages = convert_input(input_).to_messages()
    except (ValueError, TypeError, AttributeError, KeyError):
        msgs = kwargs.get("messages")
        if isinstance(msgs, list):
            return [msg for msg in msgs if isinstance(msg, BaseMessage)]
        return []
    if not isinstance(messages, list):
        return []
    return messages


def _attach_reasoning_to_payload(payload: dict[str, Any], source_messages: list[Any]) -> dict[str, Any]:
    from langchain_core.messages import AIMessage

    messages_out = payload.get("messages")
    if not isinstance(messages_out, list):
        return payload
    ai_index = 0
    for msg_dict in messages_out:
        if not isinstance(msg_dict, dict) or msg_dict.get("role") != "assistant":
            continue
        while ai_index < len(source_messages) and not isinstance(source_messages[ai_index], AIMessage):
            ai_index += 1
        if ai_index >= len(source_messages):
            break
        src = source_messages[ai_index]
        ai_index += 1
        reasoning = src.additional_kwargs.get("reasoning_content") if isinstance(src, AIMessage) else None
        if reasoning:
            msg_dict["reasoning_content"] = reasoning
    return payload


def _adapt_codex_instructions(payload: dict[str, Any], source_messages: list[Any]) -> None:
    """Extract the leading system prompt; retain later instructions in place.

    Explicit instructions (including an empty value) take precedence over
    extraction. Inspect the source role because the SDK may already have
    converted system to developer for some models. Only flatten text blocks;
    preserve structured content as a developer message rather than losing it.
    """
    from langchain_core.messages import SystemMessage

    items = payload["input"]
    extra_body = payload.get("extra_body")
    explicit = "instructions" in payload or (isinstance(extra_body, dict) and "instructions" in extra_body)
    if not explicit and source_messages and isinstance(source_messages[0], SystemMessage) and items:
        source = source_messages[0]
        first = items[0]
        if source.additional_kwargs.get("__openai_role__", "system") == "system" and first.get("role") in (
            "system",
            "developer",
        ):
            content = first.get("content")
            instructions = content if isinstance(content, str) else None
            if isinstance(content, list) and all(
                isinstance(block, dict)
                and block.get("type") in ("text", "input_text")
                and isinstance(block.get("text"), str)
                for block in content
            ):
                instructions = "\n\n".join(block["text"] for block in content)
            if instructions is not None:
                payload["instructions"] = instructions
                items = items[1:]
    payload["input"] = [
        {**item, "role": "developer"} if isinstance(item, dict) and item.get("role") == "system" else item
        for item in items
    ]


def _get_reasoning_aware_chat_openai(base_cls: type[Any]) -> type[Any]:
    """Return a ``ChatOpenAI`` subclass that round-trips ``reasoning_content``.

    Uses module-level memoisation keyed on the base class; the subclass is
    built once per (process, base class) pair.

    The subclass works by:

    * **Parse**: after ``super()._create_chat_result(...)`` runs, walk the
      raw ``choices`` array and copy each ``reasoning_content`` field into
      the matching ``AIMessage.additional_kwargs``.
    * **Serialize**: after ``super()._get_request_payload(...)`` runs, walk
      the assistant entries in ``payload["messages"]`` (chat/completions
      shape) and re-attach ``reasoning_content`` from the source
      ``AIMessage.additional_kwargs``.

    No module-level helpers are mutated, so the subclass is safe under
    concurrent use.
    """
    cached = _REASONING_AWARE_CHAT_OPENAI.get(id(base_cls))
    if cached is not None:
        return cached

    class _ReasoningAwareChatOpenAI(base_cls):  # type: ignore[misc]
        """ChatOpenAI subclass that round-trips ``reasoning_content``."""

        def _generate(self, *args: Any, **kwargs: Any) -> Any:
            try:
                return super()._generate(*args, **kwargs)
            except Exception as exc:
                fallback = _fallback_model_for(self, exc, kwargs)
                if fallback is None:
                    raise
                return _mark_api_fallback_result(fallback._generate(*args, **kwargs))

        async def _agenerate(self, *args: Any, **kwargs: Any) -> Any:
            try:
                return await super()._agenerate(*args, **kwargs)
            except Exception as exc:
                fallback = _fallback_model_for(self, exc, kwargs)
                if fallback is None:
                    raise
                return _mark_api_fallback_result(await fallback._agenerate(*args, **kwargs))

        def _stream(self, *args: Any, **kwargs: Any) -> Iterator[Any]:
            yielded = False
            try:
                for chunk in super()._stream(*args, **kwargs):
                    yielded = True
                    yield chunk
            except Exception as exc:
                fallback = None if yielded else _fallback_model_for(self, exc, kwargs)
                if fallback is None:
                    raise
                for chunk in fallback._stream(*args, **kwargs):
                    yield _mark_api_fallback_chunk(chunk)

        async def _astream(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any]:
            yielded = False
            try:
                async for chunk in super()._astream(*args, **kwargs):
                    yielded = True
                    yield chunk
            except Exception as exc:
                fallback = None if yielded else _fallback_model_for(self, exc, kwargs)
                if fallback is None:
                    raise
                async for chunk in fallback._astream(*args, **kwargs):
                    yield _mark_api_fallback_chunk(chunk)

        def _create_chat_result(self, response: Any, generation_info: dict[str, Any] | None = None) -> Any:
            return _copy_reasoning_from_response(super()._create_chat_result(response, generation_info), response)

        def _convert_chunk_to_generation_chunk(
            self,
            chunk: dict[str, Any],
            default_chunk_class: type[Any],
            base_generation_info: dict[str, Any] | None,
        ) -> Any:
            return _copy_reasoning_from_chunk(
                super()._convert_chunk_to_generation_chunk(chunk, default_chunk_class, base_generation_info),
                chunk,
            )

        def _get_request_payload(self, input_: Any, *, stop: list[str] | None = None, **kwargs: Any) -> dict[str, Any]:
            input_ = _sanitize_input_messages(input_)
            payload: dict[str, Any] = super()._get_request_payload(input_, stop=stop, **kwargs)
            if getattr(self, "_harness_codex", False):
                source_messages = _source_messages_for_payload(input_, kwargs, self._convert_input)
                _adapt_codex_instructions(payload, source_messages)
            messages_out = payload.get("messages")
            if not isinstance(messages_out, list):
                return payload
            supported: set[str] = getattr(self, "_harness_supported_input", set()) or {"text", "image"}
            if "image" not in supported:
                _strip_unsupported_content_types(messages_out)
            source_messages = _source_messages_for_payload(input_, kwargs, self._convert_input)
            if not source_messages:
                return payload
            return _attach_reasoning_to_payload(payload, source_messages)

    _REASONING_AWARE_CHAT_OPENAI[id(base_cls)] = _ReasoningAwareChatOpenAI
    return _ReasoningAwareChatOpenAI


# ---------------------------------------------------------------------------
# Legacy image block sanitization
# ---------------------------------------------------------------------------


def _sanitize_input_messages(input_: Any) -> Any:
    """Sanitize BaseMessage content before LangChain's block translator runs.

    Processes the input in-place when it's a list of BaseMessage objects.
    Converts Anthropic-style ``{"type": "image", "source": {...}}`` blocks
    (which LangChain can't handle) to the v1 standard format.
    """
    if not isinstance(input_, list):
        return input_
    from langchain_core.messages import BaseMessage

    for msg in input_:
        if not isinstance(msg, BaseMessage):
            continue
        content = msg.content
        if not isinstance(content, list):
            continue
        _sanitize_content_blocks(content)
    return input_


def _sanitize_content_blocks(content: list[Any]) -> None:
    """Fix legacy image blocks in a content block list in-place."""
    import base64 as _b64
    from pathlib import Path as _Path
    from urllib.parse import unquote as _unquote
    from urllib.parse import urlparse as _urlparse

    for i, block in enumerate(content):
        if not isinstance(block, dict):
            continue
        if block.get("type") != "image":
            continue
        source = block.get("source")
        if not isinstance(source, dict):
            continue
        # Blocks with top-level `base64` are already v1-compatible
        if "base64" in block:
            continue

        src_type = source.get("type", "")
        if src_type == "base64":
            data = source.get("data", "")
            mime = source.get("media_type", "") or "application/octet-stream"
            content[i] = {"type": "image", "base64": data, "mime_type": mime}
        elif src_type == "url":
            url = source.get("url", "")
            mime = source.get("media_type", "") or "image/png"
            if url.startswith("file://"):
                parsed = _urlparse(url)
                local_path = _Path(_unquote(parsed.path))
                if local_path.is_file():
                    try:
                        raw = local_path.read_bytes()
                        content[i] = {
                            "type": "image",
                            "base64": _b64.b64encode(raw).decode(),
                            "mime_type": mime,
                        }
                        continue
                    except OSError:
                        pass
            # Can't resolve — replace with text placeholder
            filename = block.get("filename", "") or url.rsplit("/", 1)[-1] or "image"
            content[i] = {"type": "text", "text": f"[image: {filename}]"}
        else:
            filename = block.get("filename", "") or "image"
            content[i] = {"type": "text", "text": f"[image: {filename}]"}


# ---------------------------------------------------------------------------
# Content-type filtering for text-only models
# ---------------------------------------------------------------------------

# Block types that require vision/multimodal support.
_IMAGE_CONTENT_TYPES: frozenset[str] = frozenset({"image_url", "image", "input_image"})


def _strip_unsupported_content_types(messages: list[Any]) -> None:
    """Remove image content blocks in-place from messages for text-only models.

    When conversation history contains ``image_url`` blocks (e.g. from a
    prior turn handled by a multimodal model) and the current model only
    supports text, sending those blocks causes a 400::

        unknown variant image_url, expected text

    This function:
    - Converts multipart content lists to text-only (drops image blocks,
      keeps text blocks).
    - If all content blocks are images, replaces with ``"[image]"`` so the
      message isn't empty.
    - Leaves string content and non-list content untouched.
    """
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue

        # Filter: keep only text blocks.
        text_parts: list[Any] = []
        had_image = False
        for block in content:
            if isinstance(block, dict):
                btype = block.get("type", "")
                if btype in _IMAGE_CONTENT_TYPES:
                    had_image = True
                    continue
            # Keep text blocks and any other unknown types.
            text_parts.append(block)

        if not had_image:
            # No images found — nothing to do for this message.
            continue

        if not text_parts:
            # All blocks were images — replace with placeholder.
            msg["content"] = "[image]"
        elif len(text_parts) == 1 and isinstance(text_parts[0], dict) and text_parts[0].get("type") == "text":
            # Single text block remaining — collapse to a plain string
            # for maximum compatibility.
            msg["content"] = text_parts[0].get("text", "")
        else:
            msg["content"] = text_parts


def _inject_model_token_limits(instance: BaseChatModel, model: ModelConfig) -> None:
    """Inject model context metadata into the LangChain profile.

    DeepAgents' ``SummarizationMiddleware`` reads ``model.profile["max_input_tokens"]``
    to switch from conservative fixed-count fallbacks to fraction-based thresholds
    (85% trigger, 10% keep).  LangChain only populates ``.profile`` for OpenAI
    first-party models; for all other providers it is ``None``.

    When ``max_input_tokens > 0``, we set the value directly so that all models
    — including DeepSeek, Qwen, Hunyuan, etc. — benefit from accurate context
    management.  When the model already has a profile with ``max_input_tokens``
    (i.e. an OpenAI first-party model), the harness value *overwrites* it so
    that manually configured limits take precedence.
    """
    max_input_tokens = model.max_input_tokens
    context_window = model.effective_context_window
    max_output_tokens = model.max_output_tokens
    if max_input_tokens <= 0 and context_window <= 0 and max_output_tokens <= 0:
        return
    profile = getattr(instance, "profile", None)
    if not isinstance(profile, dict):
        # profile is None or some unexpected type — replace with a minimal dict.
        with contextlib.suppress(AttributeError, TypeError):
            object.__setattr__(instance, "profile", {})
        profile = getattr(instance, "profile", None)
    if not isinstance(profile, dict):
        return
    if max_input_tokens > 0:
        profile["max_input_tokens"] = max_input_tokens
    if context_window > 0:
        profile["context_window"] = context_window
    if max_output_tokens > 0:
        profile["max_output_tokens"] = max_output_tokens
    # Keep immutable baselines outside the mutable profile. Per-request output
    # reservations may temporarily lower profile["max_input_tokens"].
    with contextlib.suppress(AttributeError, TypeError):
        object.__setattr__(instance, "_harness_max_input_tokens", max_input_tokens)
        object.__setattr__(instance, "_harness_context_window", context_window)
        object.__setattr__(instance, "_harness_max_output_tokens", max_output_tokens)


def _stamp_native_tool_search_capability(
    instance: BaseChatModel,
    provider: str,
    enabled: bool,
) -> None:
    """Attach Harness-only capability metadata to a routed model instance."""
    with contextlib.suppress(AttributeError, TypeError):
        object.__setattr__(instance, "_harness_native_tool_search", enabled)
        object.__setattr__(instance, "_harness_tool_search_provider", provider)


def _build_anthropic(provider: ProviderConfig, model: ModelConfig, *, max_retries: int | None = None) -> BaseChatModel:
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "langchain-anthropic is required for the anthropic protocol. Install with: pip install langchain-anthropic",
        ) from exc

    kwargs: dict[str, Any] = {
        "model": model.id,
        "api_key": provider.api_key,
    }
    if max_retries is not None:
        kwargs["max_retries"] = max_retries
    # ChatAnthropic accepts ``base_url`` for proxy/relay configurations.
    if provider.base_url:
        kwargs["base_url"] = provider.base_url
    if provider.headers:
        kwargs["default_headers"] = dict(provider.headers)
    # Enable extended thinking when model.thinking is explicitly True.
    if model.thinking is True:
        kwargs["thinking"] = {"type": "adaptive"}
    instance_a: BaseChatModel = ChatAnthropic(**kwargs)
    if provider.session_header:
        bind_anthropic_session_header(instance_a, provider.session_header)
    _stamp_native_tool_search_capability(instance_a, provider.protocol, model.native_tool_search)
    _inject_model_token_limits(instance_a, model)
    return instance_a


def _build_bedrock(provider: ProviderConfig, model: ModelConfig, *, max_retries: int | None = None) -> BaseChatModel:
    try:
        from langchain_aws import ChatBedrockConverse
    except ImportError as exc:
        raise ImportError(
            "langchain-aws is required for the bedrock protocol. Install with: pip install 'octop-harness[bedrock]'",
        ) from exc

    # Bedrock auth is typically AWS-credential-driven; api_key/base_url here
    # are accepted for symmetry but not all combinations are meaningful.
    kwargs: dict[str, Any] = {"model": model.id}
    if provider.headers:
        kwargs["additional_model_request_fields"] = dict(provider.headers)
    if max_retries is not None:
        from botocore.config import Config

        kwargs["config"] = Config(retries={"total_max_attempts": max_retries + 1})
    instance_b: BaseChatModel = ChatBedrockConverse(**kwargs)
    _inject_model_token_limits(instance_b, model)
    return instance_b


__all__ = ["ChatModelFactory", "ModelAccess", "build_chat_model"]
