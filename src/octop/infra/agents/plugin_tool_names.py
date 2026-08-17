"""Sanitize plugin tool names for strict LLM tool-name APIs.

Plugin authors register tools with ``ctx.tool("中文名", fn, ...)``; the harness
passes that name straight into the function-calling schema, but most LLM APIs
only accept ``^[a-zA-Z0-9_-]{1,64}$``. Mirroring the MCP-side fix
(``harness_agent.mcp.sanitize_llm_tool_name``) this module rewrites non-conforming
plugin tool names to legal ASCII names:

- CJK characters are transliterated to pinyin (``天气查询`` -> ``tianqichaxun``)
  when :mod:`pypinyin` is importable; otherwise every illegal character becomes
  ``_``.
- The original name is kept in a ``[原名: ...]`` description prefix so the model
  and the user can still map the sanitized name back.
- Collisions get ``_2``/``_3`` suffixes and results are truncated to 64 chars.

Routing is unaffected: ``ToolNode`` matches the exposed name and the underlying
plugin function is untouched. Config keys (``config_json.plugins``) keep using
the original names.
"""

from __future__ import annotations

import re
from typing import Any

_LLM_TOOL_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_ILLEGAL_CHARS_RE = re.compile(r"[^a-zA-Z0-9_-]+")
_MAX_NAME_LEN = 64

_ORIGINAL_NAME_PREFIX = "[原名: {name}] "


def _transliterate(name: str) -> str:
    """Return an ASCII-ish rendering of ``name`` (pinyin when possible)."""
    try:
        from pypinyin import lazy_pinyin  # noqa: PLC0415
    except ImportError:
        # Zero-dependency fallback: mirror MCP's underscore substitution.
        return _ILLEGAL_CHARS_RE.sub("_", name)
    syllables = lazy_pinyin(name, errors="default")
    joined = "".join(str(part) for part in syllables if str(part))
    ascii_joined = _ILLEGAL_CHARS_RE.sub("_", joined)
    return ascii_joined


def _dedupe(candidate: str, used: set[str]) -> str:
    if candidate not in used:
        return candidate
    suffix = 2
    while f"{candidate}_{suffix}" in used:
        suffix += 1
    return f"{candidate}_{suffix}"


def sanitize_plugin_tool_name(name: str, *, used: set[str] | None = None) -> str:
    """Return a legal LLM tool name for ``name``, unique against ``used``."""
    used = used if used is not None else set()
    if _LLM_TOOL_NAME_RE.match(name):
        candidate = _dedupe(name, used)
        used.add(candidate)
        return candidate
    candidate = _transliterate(name).strip("_") or "plugin_tool"
    if len(candidate) > _MAX_NAME_LEN:
        # Leave room for a possible dedupe suffix (_2, _3, ...).
        candidate = candidate[: _MAX_NAME_LEN - 4].rstrip("_") or "plugin_tool"
    candidate = _dedupe(candidate, used)
    used.add(candidate)
    return candidate


def sanitize_plugin_tool_names(
    tools: list[Any],
    *,
    reserved: frozenset[str] | set[str] = frozenset(),
) -> list[Any]:
    """Rewrite illegal plugin tool names in place and return ``tools``.

    ``reserved`` holds names already taken by other tools on the same agent
    (cron/knowledge/team tools) so sanitized names cannot shadow them.
    """
    used: set[str] = set(reserved)
    for tool in tools:
        original = str(getattr(tool, "name", ""))
        sanitized = sanitize_plugin_tool_name(original, used=used)
        if sanitized == original:
            continue
        tool.name = sanitized
        description = str(getattr(tool, "description", "") or "")
        tool.description = _ORIGINAL_NAME_PREFIX.format(name=original) + description
    return tools
