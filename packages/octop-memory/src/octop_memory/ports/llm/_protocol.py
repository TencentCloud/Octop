"""LLMClient Protocol — the interface every LLM call goes through."""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

LLMTier = Literal["light", "heavy"]
"""LLM workload tier.

- ``light``: per-session_end candidate extraction, 5-check escalation,
  alias disambiguation. ~5-10 calls/day for a heavy user. Uses smaller /
  cheaper / lower-latency models (e.g. host's small-tier Ollama).
- ``heavy``: daily cross-session candidate consolidation, entity page
  re-summarization. ~1-2 calls/day. Uses the host's strongest model.

Tier selection is the host's call (``HostLLMClient`` translates ``light``/
``heavy`` to whatever model identifier the host expects). For
``OpenAICompatClient``, both tiers use ``model`` unless ``model_heavy``
is set — that's fine for dev validation, the production path gets the
real fallback chain.
"""


DEFAULT_EXTRACT_MAX_TOKENS = 2048
"""Default soft cap for memory-extraction completions.

Extraction prompts ask for bounded JSON (candidates / episodes), so a few
thousand tokens is plenty. Without a cap, a reasoning-heavy model may chain
on the full remaining context window and run far past the client read
timeout — bounding the budget bounds the worst-case wall time (TencentCloud/Octop#1360).
"""


@runtime_checkable
class LLMClient(Protocol):
    """Abstract interface for LLM completion calls.

    Implementations:
    - ``MockLLMClient`` for tests
    - ``OpenAICompatClient`` for self-hosted endpoints and dev-only
      prompt validation (Ollama's OpenAI-compatible ``/v1`` endpoint)
    - ``OpenClawLLMClient`` / ``HermesLLMClient`` (added when host adapters
      are wired) wrap the host's LLM API

    The interface intentionally does not expose model selection, fallback
    chain, or rate limit knobs — those are the host's responsibility (D25).
    Plugin code only specifies the workload tier.
    """

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
        """Run a single completion.

        Args:
            prompt: User-side prompt (the main payload).
            tier: Workload tier; the implementation maps this to a concrete
                model name.
            system: Optional system message prepended to the prompt.
            max_tokens: Soft cap for response length. Implementations
                may ignore it if the host doesn't expose it.
            temperature: 0.0 = deterministic, 1.0 = creative. Default
                depends on implementation.
            response_format: ``"json"`` requests structured output mode if
                the implementation supports it; otherwise the implementation
                must still return a string and the caller handles parsing.

        Returns:
            The completion text (already stripped of any wrapper formatting).

        Raises:
            ``LLMClientError`` (or subclass) on transport / model failure.
            The extractor / promotion worker catches this and falls back
            to ``extractor_failed`` / ``needs_review`` — never propagates
            into user-facing flows.
        """
        ...


class LLMClientError(RuntimeError):
    """Raised when an ``LLMClient`` cannot complete a request.

    Callers (extractor / promotion worker) must catch this and degrade
    gracefully — never let it bubble up into the user's main reply path.
    """


class NoopLLMClient:
    """A no-op client that immediately raises ``LLMClientError``.

    Used when no real LLM backend is available (host doesn't expose LLM,
    Ollama not installed, etc.). Lets memory core continue to function for
    L0 mirror write + raw FTS recall while signalling extraction is
    unavailable.
    """

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
        raise LLMClientError("no LLM backend configured — install host LLM adapter or pass --dev-llm to use Ollama")
