"""Optional web-search tools.

Each provider lives in its own module so the heavy / region-locked
dependencies (``langchain-tavily``, ``langchain-community``,
``google-api-python-client``, ``openai`` …) only get imported when the
caller actually wants them. The registry in :mod:`._registry` decides
what to expose based on environment variables (just like
LightClaw's original ``builtins.py``).
"""

from __future__ import annotations

from octop_harness.builtin.tools.web_search._registry import (
    WebSearchToolName,
    load_web_search_tools,
)

__all__ = ["WebSearchToolName", "load_web_search_tools"]
