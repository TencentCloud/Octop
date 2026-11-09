"""Octop — smarter self-hosted AI assistant (multi-user, multi-agent)."""

from __future__ import annotations

from octop.infra.utils.httpx_proxy import install_httpx_cidr_no_proxy

__version__ = "1.0.3b4"

# httpx 0.28 treats NO_PROXY CIDR as an exact IP (see issue #1347). Patch once
# at import so CLI, ``octop run``, and in-process harness clients all honor it.
install_httpx_cidr_no_proxy()

# langchain-anthropic 1.7.x crashes on message_delta events carrying dict-shaped
# context_management from recent Anthropic API updates. Patch once at import.
try:
    from octop.infra.agents.providers.anthropic_compat import (
        patch_langchain_anthropic_context_management,
    )

    patch_langchain_anthropic_context_management()
except Exception:
    pass

