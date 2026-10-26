"""Registry: pick the right web-search tools based on env vars / config.

Each provider declares a *required env-var tuple*. A provider is
considered "available" iff every variable in its tuple is non-empty.
Providers with an empty tuple (``()``) need no configuration and are
therefore always available — that's the case for ``searchfree``, the
zero-config public fallback. ``you`` also needs no env vars when named
explicitly, but only joins ``auto`` once ``YDC_API_KEY`` is set.

The registry exposes two entry points:

- :func:`load_web_search_tools` — return the LangChain ``@tool``
  objects matching a user-supplied policy.
- :data:`WEB_SEARCH_PROVIDERS` — the canonical mapping, surfaced for
  introspection / documentation.

Policies accepted by ``HarnessAgentConfig.web_search_tools``:

- ``False`` (default): no web-search tools are auto-loaded.
- ``True`` / ``"auto"``: every provider whose env vars are present is
  loaded. ``searchfree`` always qualifies; ``you`` joins only when
  ``YDC_API_KEY`` is set (see ``_AUTO_REQUIRED_ENV``).
- ``"all"``: every provider is loaded *unconditionally* — useful for
  testing; tools without their env var return an "Error: ..." string
  on invocation.
- ``Iterable[str]``: explicit list of provider names. Unknown names
  raise ``ValueError``; missing env vars raise ``RuntimeError`` so
  misconfiguration surfaces at agent construction time, not at first
  tool call.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any, Literal, cast

WebSearchToolName = Literal[
    "tavily", "brave", "doubao", "deepseek", "exa", "google", "kimi", "yuanbao", "searchfree", "you"
]

# ``provider name → (required env vars, lazy loader returning a langchain tool)``.
# Loaders are deliberately lazy so importing this module is cheap.


def _load_tavily() -> Any:
    from octop_harness.builtin.tools.web_search.tavily import tavily_search

    return tavily_search


def _load_brave() -> Any:
    from octop_harness.builtin.tools.web_search.brave import brave_search

    return brave_search


def _load_doubao() -> Any:
    from octop_harness.builtin.tools.web_search.doubao import doubao_search

    return doubao_search


def _load_deepseek() -> Any:
    from octop_harness.builtin.tools.web_search.deepseek import deepseek_search

    return deepseek_search


def _load_exa() -> Any:
    from octop_harness.builtin.tools.web_search.exa import exa_search

    return exa_search


def _load_google() -> Any:
    from octop_harness.builtin.tools.web_search.google import google_search

    return google_search


def _load_kimi() -> Any:
    from octop_harness.builtin.tools.web_search.kimi import kimi_search

    return kimi_search


def _load_yuanbao() -> Any:
    from octop_harness.builtin.tools.web_search.yuanbao import yuanbao_search

    return yuanbao_search


def _load_searchfree() -> Any:
    from octop_harness.builtin.tools.web_search.searchfree import searchfree_search

    return searchfree_search


def _load_you() -> Any:
    from octop_harness.builtin.tools.web_search.you import you_search

    return you_search


WEB_SEARCH_PROVIDERS: dict[WebSearchToolName, tuple[tuple[str, ...], Any]] = {
    "tavily": (("TAVILY_API_KEY",), _load_tavily),
    "brave": (("BRAVE_API_KEY",), _load_brave),
    "doubao": (("DOUBAO_SEARCH_API_KEY",), _load_doubao),
    "deepseek": (("DEEPSEEK_API_KEY",), _load_deepseek),
    "exa": (("EXA_API_KEY",), _load_exa),
    "google": (("GOOGLE_API_KEY", "GOOGLE_CSE_ID"), _load_google),
    "kimi": (("MOONSHOT_API_KEY",), _load_kimi),
    "yuanbao": (("TENCENTCLOUD_WSA_APIKEY",), _load_yuanbao),
    # ``searchfree`` needs no env vars — empty tuple makes it always
    # available under the ``auto`` policy.
    "searchfree": ((), _load_searchfree),
    # ``you`` works without a key when named explicitly; ``YDC_API_KEY``
    # raises its limits. See ``_AUTO_REQUIRED_ENV`` for the ``auto`` gate.
    "you": ((), _load_you),
}

# Providers that need no env vars when named explicitly but should only join
# the ``auto`` policy once the user has configured them. This keeps the
# default tool set unchanged for users who never set the variable.
_AUTO_REQUIRED_ENV: dict[str, tuple[str, ...]] = {
    "you": ("YDC_API_KEY",),
}


def _provider_available(env_vars: tuple[str, ...]) -> bool:
    return all(os.getenv(name) for name in env_vars)


def _missing_env(env_vars: tuple[str, ...]) -> list[str]:
    return [name for name in env_vars if not os.getenv(name)]


def load_web_search_tools(
    policy: bool | Literal["auto", "all"] | Iterable[str] = False,
) -> list[Any]:
    """Resolve a web-search policy into a list of LangChain tools.

    See the module docstring for the full list of accepted policies.
    """
    if policy is False:
        return []
    if policy is True or policy == "auto":
        out: list[Any] = []
        for name, (env_vars, loader) in WEB_SEARCH_PROVIDERS.items():
            if _provider_available(env_vars + _AUTO_REQUIRED_ENV.get(name, ())):
                out.append(loader())
        return out
    if policy == "all":
        return [loader() for _, loader in WEB_SEARCH_PROVIDERS.values()]

    # Explicit list.
    names = list(policy)
    unknown = [n for n in names if n not in WEB_SEARCH_PROVIDERS]
    if unknown:
        raise ValueError(
            f"Unknown web-search provider(s): {unknown}. Valid names: {sorted(WEB_SEARCH_PROVIDERS)}.",
        )
    out = []
    for raw_name in names:
        # ``raw_name`` is checked against ``WEB_SEARCH_PROVIDERS`` above;
        # mypy can't narrow ``str`` → ``WebSearchToolName`` without help.
        name = cast("WebSearchToolName", raw_name)
        env_vars, loader = WEB_SEARCH_PROVIDERS[name]
        missing = _missing_env(env_vars)
        if missing:
            raise RuntimeError(
                f"Web-search provider {name!r} requested but env var(s) "
                f"missing: {missing}. Either set them or remove "
                f"{name!r} from web_search_tools.",
            )
        out.append(loader())
    return out


__all__ = [
    "WEB_SEARCH_PROVIDERS",
    "WebSearchToolName",
    "load_web_search_tools",
]
