"""LLM client abstraction for candidate extraction & promotion escalation.

Design (D25):
- **Production path**: 100% host LLM via the ``LLMClient`` protocol. The
  bridge layer (``OpenClawLLMClient`` / ``HermesLLMClient`` etc.) wraps the
  host's LLM completion API and is injected at adapter setup time. Memory
  core code never imports these directly.
- **Testing**: ``MockLLMClient`` returns canned responses keyed by prompt
  signature. All unit tests use this — no network calls.
- **Production (self-hosted bridge)**: ``OpenAICompatClient`` — the one
  exception to "100% host LLM". OpenClaw's plugin API does not expose a
  host LLM completion surface to plugins, so claw production deployments
  configure an OpenAI-compatible endpoint in the plugin config; the TS
  shell forwards it to the bridge via ``--config-json`` and the bridge
  constructs this client for extraction / promotion / page regen.

``OpenAICompatClient`` also covers local development: Ollama serves an
OpenAI-compatible API at ``http://localhost:11434/v1``, which the hidden
CLI flag ``--dev-llm=ollama:<model>`` points at.

Why is there no dedicated remote API client (D25)?
The plugin runs inside a Claw-like host that already has model credentials
configured; a second credential set degrades UX. That still holds for
hosts that DO inject an ``LLMClient`` — ``OpenAICompatClient`` is only
the fallback for hosts (current OpenClaw) that don't.
"""

from __future__ import annotations

from octop_memory.ports.llm._protocol import (
    DEFAULT_EXTRACT_MAX_TOKENS,
    LLMClient,
    LLMClientError,
    LLMTier,
    NoopLLMClient,
)
from octop_memory.ports.llm.mock import MockLLMClient
from octop_memory.ports.llm.openai_compat import DEFAULT_LLM_API_KEY_ENV, OpenAICompatClient

__all__ = [
    "DEFAULT_EXTRACT_MAX_TOKENS",
    "DEFAULT_LLM_API_KEY_ENV",
    "LLMClient",
    "LLMClientError",
    "LLMTier",
    "MockLLMClient",
    "NoopLLMClient",
    "OpenAICompatClient",
]
