"""``SkillFilterMiddleware`` — agent-level disable + per-request skill filtering."""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, cast

from deepagents.middleware.skills import SkillMetadata
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.types import AgentState
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from octop_harness.middleware.runtime import runtime_config
from octop_harness.skills.catalog import skill_identity_keys

if TYPE_CHECKING:
    from octop_harness.config import HarnessAgentConfig

logger = logging.getLogger(__name__)

_FS_SKILL_TOOLS = frozenset({"ls", "read_file", "glob", "grep", "write_file", "edit_file", "delete"})
_SHELL_SKILL_TOOLS = frozenset({"execute", "bash", "shell"})
_BASE_SKILL_DIR_MARKERS = ("/skills/", "/_builtin_skills/")
_SLUG_CUT_RE = re.compile(r"[*?\[\]\s'\"\\]")
# Row-start ``/slug`` or ``/slug args``. Reject ``/root/ddd`` (path).
_SKILL_INVOKE_RE = re.compile(r"^\s*/([a-zA-Z][\w-]*)(?:\s|$)")


def _skill_dir_markers(system_files_path: str = "") -> tuple[str, ...]:
    """Path markers that introduce a skill slug segment (jail + optional prefix)."""
    from octop_harness.backends.workspace import normalize_system_files_path

    prefix = normalize_system_files_path(system_files_path)
    if not prefix:
        return _BASE_SKILL_DIR_MARKERS
    return (
        f"/{prefix}/skills/",
        f"/{prefix}/_builtin_skills/",
        *_BASE_SKILL_DIR_MARKERS,
    )


def _tool_base_name(name: str) -> str:
    trimmed = name.strip()
    slash = trimmed.rfind("/")
    return trimmed[slash + 1 :] if slash >= 0 else trimmed


def _iter_arg_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, dict):
        out: list[str] = []
        for item in value.values():
            out.extend(_iter_arg_strings(item))
        return out
    if isinstance(value, (list, tuple)):
        nested: list[str] = []
        for item in value:
            nested.extend(_iter_arg_strings(item))
        return nested
    return []


def _skill_slugs_from_text(
    text: str,
    *,
    system_files_path: str = "",
) -> list[str]:
    """Return skill directory slugs mentioned under ``skills/`` or ``_builtin_skills/``."""
    normalized = str(text).replace("\\", "/").strip()
    if not normalized:
        return []
    haystack = normalized if normalized.startswith("/") else f"/{normalized}"
    slugs: list[str] = []
    seen: set[str] = set()
    for marker in _skill_dir_markers(system_files_path):
        start = 0
        while True:
            idx = haystack.find(marker, start)
            if idx == -1:
                break
            rest = haystack[idx + len(marker) :]
            raw = rest.split("/", 1)[0]
            slug = _SLUG_CUT_RE.split(raw, maxsplit=1)[0].strip()
            if slug and slug not in {".", ".."} and slug not in seen:
                seen.add(slug)
                slugs.append(slug)
            start = idx + len(marker)
    return slugs


def disabled_skill_block_reason(
    text: str | None,
    *,
    disabled: frozenset[str] | set[str],
    system_files_path: str = "",
) -> str | None:
    """Return an error message when *text* names a disabled skill directory.

    Only ``skills/<slug>`` and ``_builtin_skills/<slug>`` (plus the same under
    ``system_files_path`` when set) count. Unrelated paths that happen to share
    a slug are ignored.
    """
    if not disabled or not text:
        return None
    disabled_keys = set(disabled)
    for slug in _skill_slugs_from_text(text, system_files_path=system_files_path):
        keys = {slug, *skill_identity_keys({"name": slug, "slug": slug})}
        if keys & disabled_keys:
            return f"Error: skill {slug!r} is disabled and cannot be accessed via filesystem tools"
    return None


def slash_skill_slug(text: str) -> str | None:
    """Return the ``/slug`` name when *text* is a skill-style invoke, else ``None``."""
    match = _SKILL_INVOKE_RE.match(text)
    return match.group(1).lower() if match else None


def render_slash_skill_prompt(*, language: str) -> str:
    """Stable system-prompt rule for a leading ``/name`` skill invoke.

    Baked into the compiled system prompt (not per-turn) so the prefix stays
    cacheable. The token itself lives in the user message; this text does
    not name a slug.
    """
    if language == "en":
        return (
            "If the user message starts with /name (a skill-style token, not a "
            "path like /root/file), treat that as an explicit skill invoke: match "
            "/name against a skill's name or slug in this system prompt's skill "
            "list, then immediately read that skill's SKILL.md and follow it "
            "before other tools or skills. Prefer the named skill over generic "
            "approaches. If no such skill exists, treat the message as ordinary "
            "chat and do not invent a skill."
        )
    return (
        "若用户消息以 /name 开头 (skill 点名, 不是 /root/file 这类路径), "
        "表示点名使用该 skill: 用 /name 对照本系统提示词 skill 列表中的 "
        "name 或 slug; 命中后立刻先读对应 SKILL.md 并按其执行, "
        "优先于其它工具与其它 skill, 不要先用通用做法绕开. "
        "没有对应 skill 则把这条当普通对话, 不要编造 skill."
    )


class SkillFilterMiddleware(AgentMiddleware[Any, Any]):
    """Apply ``HarnessAgentConfig.skills_disabled`` and optional per-turn filters.

    Agent-level ``skills_disabled`` is always honoured. When
    ``configurable["skills"]`` is also present (including an empty list),
    the remaining skills are further restricted to that allow-list (API /
    scripts). Composer hosts should put ``/slug`` in the user text; a
    stable ``/name`` rule is compiled into the system prompt (not injected
    per turn).

    Disabled skills are removed from ``skills_metadata`` so they do not
    appear in the system prompt. Filesystem tools and ``execute``/``bash``
    are blocked when any string argument names ``skills/<slug>`` or
    ``_builtin_skills/<slug>`` for a disabled skill (including glob patterns
    and shell command lines). Workspace-wide ``grep``/``glob`` with no skill
    path in the args is not rewritten.

    System-prompt rendering is fully delegated to the downstream
    ``SkillsMiddleware`` added by :func:`deepagents.create_deep_agent`.
    This middleware exclusively updates state so that ``SkillsMiddleware``
    builds one correct, filtered section — avoiding duplicate sections.
    """

    def __init__(self, *, config: HarnessAgentConfig) -> None:
        self._config = config

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        return handler(self._apply_filter(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        return await handler(self._apply_filter(request))

    def _blocked_tool_message(self, request: ToolCallRequest, reason: str) -> ToolMessage:
        tool_call = request.tool_call
        return ToolMessage(
            content=reason,
            tool_call_id=str(tool_call.get("id") or ""),
            status="error",
        )

    def _tool_block_reason(self, request: ToolCallRequest) -> str | None:
        disabled = self._config.skills_disabled
        if not disabled:
            return None
        tool_call = request.tool_call
        tool_name = str(tool_call.get("name") or "")
        base = _tool_base_name(tool_name)
        if base not in _FS_SKILL_TOOLS and base not in _SHELL_SKILL_TOOLS:
            return None
        raw_args = tool_call.get("args") or {}
        prefix = str(self._config.system_files_path or "")
        for chunk in _iter_arg_strings(raw_args):
            reason = disabled_skill_block_reason(
                chunk,
                disabled=disabled,
                system_files_path=prefix,
            )
            if reason is not None:
                return reason
        return None

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        reason = self._tool_block_reason(request)
        if reason is not None:
            logger.info("SkillFilter blocked %s", request.tool_call.get("name"))
            return self._blocked_tool_message(request, reason)
        return await handler(request)

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        reason = self._tool_block_reason(request)
        if reason is not None:
            logger.info("SkillFilter blocked %s", request.tool_call.get("name"))
            return self._blocked_tool_message(request, reason)
        return handler(request)

    def _override_skills_metadata(
        self,
        request: ModelRequest,
        metadata: list[SkillMetadata],
        raw_metadata: object,
    ) -> ModelRequest:
        if metadata == list(raw_metadata) if isinstance(raw_metadata, list) else []:
            return request
        new_state = cast(
            AgentState[Any],
            {**request.state, "skills_metadata": metadata},
        )
        return request.override(state=new_state)

    def _apply_filter(self, request: ModelRequest) -> ModelRequest:
        raw_metadata = request.state.get("skills_metadata")
        metadata: list[SkillMetadata] = list(raw_metadata) if isinstance(raw_metadata, list) else []

        disabled = self._config.skills_disabled
        if disabled:
            metadata = [skill for skill in metadata if not (skill_identity_keys(skill) & disabled)]

        configurable = runtime_config(request).get("configurable") or {}
        allowed = configurable.get("skills")
        if allowed is None:
            return self._override_skills_metadata(request, metadata, raw_metadata)

        if not isinstance(allowed, list):
            logger.warning("Invalid skills filter %r; expected list[str]", allowed)
            return self._override_skills_metadata(request, metadata, raw_metadata)

        allowed_set = {str(name) for name in allowed}
        available_names = {skill["name"] for skill in metadata}
        available_slugs = {slug for skill in metadata for slug in skill_identity_keys(skill)}
        unknown = sorted(allowed_set - available_names - available_slugs)
        if unknown:
            logger.warning(
                "ChatRequest references unknown skill(s) %s; available names: %s",
                unknown,
                sorted(available_names),
            )

        filtered = [skill for skill in metadata if skill_identity_keys(skill) & allowed_set]
        return self._override_skills_metadata(request, filtered, raw_metadata)


__all__ = [
    "SkillFilterMiddleware",
    "disabled_skill_block_reason",
    "render_slash_skill_prompt",
    "slash_skill_slug",
]
