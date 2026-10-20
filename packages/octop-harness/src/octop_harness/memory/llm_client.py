"""``HarnessAgentLLMClient`` — adapt the agent's models to octop-memory.

``octop-memory``'s extractor / promotion / page-regen paths talk to the
host model through the :class:`octop_memory.ports.llm.LLMClient` protocol. This
module wraps the agent's existing :class:`ChatModelFactory` so we can reuse
the same providers and credentials the rest of the agent already uses.

Model selection
---------------
Extract uses **one** model, not a light/heavy pair. Resolution order:

1. optional aux override (``aux_model``, or the legacy light/heavy aliases)
2. the live chat model (:meth:`set_current_model`)
3. the agent's ``default_model``

``tier`` only changes the timeout. If a ref fails (expired subscription,
400, missing model), ``call_llm`` tries the next one in that list.

Failure discipline
------------------
Any transport / model error is wrapped in :class:`LLMClientError` so the
plugin's extractor / promotion worker can degrade gracefully (write the
``failure_reason`` and move on) — never bubble into the user reply path.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal

import httpx
from octop_memory.ports.llm import LLMClientError, LLMTier

from octop_harness.llm.invoke_helpers import bind_call_options, build_text_messages, stringify_content

if TYPE_CHECKING:
    from octop_harness.llm.factory import ChatModelFactory

logger = logging.getLogger(__name__)

# Model ids that start a reasoning chain unless the request turns it off.
# Matched against the model id (the part after the last "/"), not the provider.
_REASONING_MODEL_RE = re.compile(
    r"(qwen3|qwen-3|qwq)",
    re.IGNORECASE,
)
ThinkingMode = Literal["auto", "off", "on"]


class HarnessAgentLLMClient:
    """Adapter from :class:`ChatModelFactory` to :class:`LLMClient`.

    Args:
        factory: The agent's model factory; used to build / cache
            ``BaseChatModel`` instances by ``"<provider>/<model>"`` ref.
        aux_model: Optional extract override. When unset, extract follows
            the live chat model and then ``default_model``.
        light_model / heavy_model: Legacy aliases for ``aux_model``. The
            first non-empty value wins; both tiers share it.
        default_model: Last-resort model ref when no aux and no live chat
            model have been recorded yet.
        light_timeout_s / heavy_timeout_s: Read-timeout overrides per tier;
            ``None`` keeps the class defaults.
        default_max_tokens: Completion budget applied when a call does not
            pass its own ``max_tokens``; ``None`` adds no client-side cap.
            Extraction always sends a budget, so this does not override
            ``memory_extract_max_tokens``.
        extra_body: Vendor request extras merged onto primary-model calls after the
            thinking switch. Matching top-level keys from here win.
            ``None`` or empty adds nothing. Extras apply only to the first
            selected model; fallback models receive their own derived options.
        max_retries: Extra attempts per model for timeout/network/408/409/429/5xx
            failures. SDK retries are disabled on isolated model instances.
        retry_backoff_s: Exponential retry delay, capped at 60 seconds.
        thinking: ``auto`` / ``off`` disable thinking for known Qwen3/QwQ
            chat-template models. Unknown models keep their own defaults;
            ``on`` leaves the server default. Main-chat thinking settings
            are not applied to this client.
    """

    # Default timeouts in seconds. Light covers per-session extraction and alias
    # disambiguation; heavy covers cross-session consolidation. Hard caps prevent
    # upstream gateway stalls or slow inference from blocking extract threads.
    DEFAULT_LIGHT_TIMEOUT_S: float = 120.0
    DEFAULT_HEAVY_TIMEOUT_S: float = 300.0

    def __init__(
        self,
        factory: ChatModelFactory,
        *,
        aux_model: str | None = None,
        light_model: str | None = None,
        heavy_model: str | None = None,
        default_model: str | None = None,
        light_timeout_s: float | None = None,
        heavy_timeout_s: float | None = None,
        default_max_tokens: int | None = None,
        extra_body: Mapping[str, object] | None = None,
        thinking: ThinkingMode = "auto",
        max_retries: int = 2,
        retry_backoff_s: float = 1.0,
    ) -> None:
        configured = _first_ref(aux_model, light_model, heavy_model)
        if configured is None and default_model is None:
            raise ValueError(
                "HarnessAgentLLMClient requires aux_model or default_model",
            )
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or not 0 <= max_retries <= 10:
            raise ValueError("max_retries must be an integer from 0 to 10")
        if (
            isinstance(retry_backoff_s, bool)
            or not isinstance(retry_backoff_s, int | float)
            or not 0 <= retry_backoff_s <= 60
        ):
            raise ValueError("retry_backoff_s must be between 0 and 60 seconds")
        self._max_retries = max_retries
        self._retry_backoff_s = retry_backoff_s
        self._factory = factory
        self._aux_model = configured
        self._default_model = default_model
        self._light_timeout_s = light_timeout_s if light_timeout_s is not None else self.DEFAULT_LIGHT_TIMEOUT_S
        self._heavy_timeout_s = heavy_timeout_s if heavy_timeout_s is not None else self.DEFAULT_HEAVY_TIMEOUT_S
        self._default_max_tokens = default_max_tokens
        self._extra_body = dict(extra_body) if extra_body else None
        self._thinking: ThinkingMode = thinking
        self._current_lock = threading.Lock()
        self._current_model: str | None = None

    def set_current_model(self, ref: str | None) -> None:
        """Record the model the user is actually chatting with.

        When no aux override is set, extract uses this ref. When aux is
        set and fails, extract retries here.
        """
        value = ref.strip() if isinstance(ref, str) and ref.strip() else None
        with self._current_lock:
            self._current_model = value

    # ------------------------------------------------------------------
    # LLMClient protocol
    # ------------------------------------------------------------------

    def call_llm(
        self,
        prompt: str,
        *,
        tier: LLMTier = "light",
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        response_format: Literal["text", "json"] = "text",
    ) -> str:
        refs = self._candidate_refs()
        if not refs:
            raise LLMClientError(f"no model configured for tier={tier!r}")

        effective_max_tokens = max_tokens if max_tokens is not None else self._default_max_tokens
        last_exc: BaseException | None = None
        for index, ref in enumerate(refs):
            try:
                return self._invoke_ref(
                    ref,
                    prompt,
                    tier=tier,
                    system=system,
                    max_tokens=effective_max_tokens,
                    temperature=temperature,
                    response_format=response_format,
                    extra_body=self._extra_body if index == 0 else None,
                )
            except Exception as exc:  # provider error types vary; try the next ref; pylint: disable=broad-except
                last_exc = exc
                next_ref = refs[index + 1] if index + 1 < len(refs) else None
                if next_ref is None:
                    break
                logger.info(
                    "HarnessAgentLLMClient: %s failed for tier=%s; falling back to %s: %r (%s)",
                    ref,
                    tier,
                    next_ref,
                    exc,
                    type(exc).__name__,
                )

        assert last_exc is not None
        failed_ref = refs[-1]
        detail = str(last_exc).strip() or type(last_exc).__name__
        raise LLMClientError(
            f"chat model {failed_ref!r} failed for tier={tier!r}: {detail}",
        ) from last_exc

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _candidate_refs(self) -> list[str]:
        """Return distinct refs: aux override, then live chat, then default."""
        with self._current_lock:
            current = self._current_model
        ordered: list[str] = []
        seen: set[str] = set()
        for ref in (self._aux_model, current, self._default_model):
            stripped = _first_ref(ref)
            if stripped is None or stripped in seen:
                continue
            seen.add(stripped)
            ordered.append(stripped)
        return ordered

    def _invoke_ref(
        self,
        ref: str,
        prompt: str,
        *,
        tier: LLMTier,
        system: str | None,
        max_tokens: int | None,
        temperature: float | None,
        response_format: Literal["text", "json"],
        extra_body: Mapping[str, object] | None,
    ) -> str:
        try:
            model = self._factory.get_chat_model(ref, max_retries=0)
        except Exception as exc:
            detail = str(exc).strip() or type(exc).__name__
            raise LLMClientError(
                f"failed to build chat model {ref!r} for tier={tier!r}: {detail}",
            ) from exc

        output_limit = getattr(model, "_harness_max_output_tokens", None)
        if max_tokens is not None and isinstance(output_limit, int) and output_limit > 0:
            max_tokens = min(max_tokens, output_limit)
        bound_model = bind_call_options(
            model,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format=response_format,
            timeout_s=self._light_timeout_s if tier == "light" else self._heavy_timeout_s,
            extra_body=_aux_extra_body(ref, self._thinking, extra_body),
        )
        messages = build_text_messages(prompt, system=system)

        for attempt in range(self._max_retries + 1):
            try:
                response = bound_model.invoke(messages)
                return stringify_content(response.content)
            except Exception as exc:
                if attempt < self._max_retries and _is_transient(exc):
                    delay = min(60.0, self._retry_backoff_s * 2**attempt)
                    logger.info(
                        "Memory LLM retry model=%s attempt=%s delay=%ss: %s",
                        ref,
                        attempt + 1,
                        delay,
                        type(exc).__name__,
                    )
                    time.sleep(delay)
                    continue
                detail = str(exc).strip() or type(exc).__name__
                raise LLMClientError(
                    f"chat model {ref!r} failed for tier={tier!r}: {type(exc).__name__}: {detail}",
                ) from exc
        raise AssertionError("unreachable")


def _is_transient(exc: BaseException) -> bool:
    """Retry transport failures and transient HTTP errors, never arbitrary 400s."""
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status in (408, 409, 429) or 500 <= status < 600
    if isinstance(exc, (TimeoutError, ConnectionError, httpx.TimeoutException, httpx.NetworkError)):
        return True
    return exc.__cause__ is not None and _is_transient(exc.__cause__)


def _aux_extra_body(
    ref: str,
    thinking: ThinkingMode,
    extra_body: Mapping[str, object] | None,
) -> dict[str, Any] | None:
    """Merge the thinking switch with caller extras.

    The switch is applied first. Caller keys replace it at the top level,
    so an explicit ``chat_template_kwargs`` wins over the automatic disable.
    """
    merged: dict[str, Any] = dict(_disable_thinking_extra_body(ref, thinking) or {})
    if extra_body:
        merged.update(extra_body)
    return merged or None


def _disable_thinking_extra_body(ref: str, mode: ThinkingMode) -> dict[str, Any] | None:
    """Return the OpenAI-compatible body that turns reasoning off, or None.

    ``enable_thinking`` is a chat-template flag used by Qwen3 / vLLM-style
    servers. Official OpenAI rejects unknown body fields, so ``auto`` only
    attaches it when the model id looks like a default-on reasoning model.
    """
    if mode == "on":
        return None
    model_id = ref.rsplit("/", 1)[-1]
    if _REASONING_MODEL_RE.search(model_id) is None:
        return None
    return {"chat_template_kwargs": {"enable_thinking": False}}


def _first_ref(*refs: str | None) -> str | None:
    for ref in refs:
        if isinstance(ref, str) and ref.strip():
            return ref.strip()
    return None


__all__ = ["HarnessAgentLLMClient"]
