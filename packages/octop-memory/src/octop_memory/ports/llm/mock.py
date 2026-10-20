"""MockLLMClient for tests — deterministic canned responses.

Usage (in a test):

    mock = MockLLMClient(
        responses={
            "extract_v2:hash-of-prompt-1": '{"candidates": [...]}',
            ...,
        },
        default_response="...",
    )
    extractor = CandidateExtractor(llm=mock, ...)

The mock is intentionally dumb — it does not pattern-match on prompt
content (that would couple tests to prompt internals). Tests register
specific (key, response) pairs OR rely on ``default_response``. Use
``calls`` to assert call ordering, tier mix, etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from octop_memory.ports.llm._protocol import LLMClientError, LLMTier


@dataclass
class _RecordedCall:
    """A single ``call_llm()`` invocation captured for test assertions."""

    prompt: str
    tier: LLMTier
    system: str | None
    response_format: Literal["text", "json"]
    max_tokens: int | None = None
    temperature: float | None = None


class MockLLMClient:
    """In-memory LLM stub used in unit tests.

    Resolution order:

    1. If ``key_fn`` returns a key that exists in ``responses``, return that.
    2. Else if ``default_response`` is set, return it.
    3. Else raise ``LLMClientError`` (forces tests to be explicit about
       what they expect).

    Set ``raise_on_call=True`` to make the mock unconditionally fail —
    useful for testing the no-LLM degradation path.
    """

    def __init__(
        self,
        *,
        responses: dict[str, str] | None = None,
        default_response: str | None = None,
        raise_on_call: bool = False,
        key_fn: object = None,
    ) -> None:
        self._responses = dict(responses or {})
        self._default = default_response
        self._raise_on_call = raise_on_call
        # ``key_fn`` defaults to a simple "first 80 chars of prompt" key so
        # tests can register responses without knowing exact hashes.
        self._key_fn = key_fn if callable(key_fn) else self._default_key
        self.calls: list[_RecordedCall] = []

    @staticmethod
    def _default_key(prompt: str) -> str:
        return prompt[:80]

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
        self.calls.append(
            _RecordedCall(
                prompt=prompt,
                tier=tier,
                system=system,
                response_format=response_format,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        )
        if self._raise_on_call:
            raise LLMClientError("mock configured to raise")

        key: str = self._key_fn(prompt) if callable(self._key_fn) else str(self._key_fn)
        if key in self._responses:
            return self._responses[key]
        if self._default is not None:
            return self._default
        raise LLMClientError(
            f"MockLLMClient: no response registered for key={key!r} and no default; "
            "register an explicit response or set default_response"
        )

    # -- Convenience helpers for tests ----------------------------------

    def queue(self, key: str, response: str) -> None:
        """Register / overwrite a response for a key."""
        self._responses[key] = response

    def reset(self) -> None:
        """Clear call history (does not clear registered responses)."""
        self.calls.clear()
