"""Shared text-assist invoke path for chat polish and form copy."""

from __future__ import annotations

import logging
from typing import Any, Literal

from octop.i18n import tr
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.llm_text import ainvoke_text
from octop.infra.utils.locale import Locale, normalize_locale

logger = logging.getLogger(__name__)

AssistKind = Literal[
    "chat.prompt",
    "expert.description",
    "expert.welcome_message",
    "team.description",
    "team.welcome_message",
    "skill_package.description",
    "skill.description",
    "skill.label_zh",
    "skill.label_en",
    "skill.summary_zh",
    "skill.summary_en",
    "skill.body",
    "knowledge_base.description",
    "connector.description",
    "bridge.notes",
    "user_group.description",
    "user_role.description",
]

ASSIST_KINDS: frozenset[str] = frozenset(
    {
        "chat.prompt",
        "expert.description",
        "expert.welcome_message",
        "team.description",
        "team.welcome_message",
        "skill_package.description",
        "skill.description",
        "skill.label_zh",
        "skill.label_en",
        "skill.summary_zh",
        "skill.summary_en",
        "skill.body",
        "knowledge_base.description",
        "connector.description",
        "bridge.notes",
        "user_group.description",
        "user_role.description",
    }
)

_FORM_KINDS: frozenset[str] = frozenset(
    {
        "expert.description",
        "expert.welcome_message",
        "team.description",
        "team.welcome_message",
        "skill_package.description",
        "skill.description",
        "skill.label_zh",
        "skill.label_en",
        "skill.summary_zh",
        "skill.summary_en",
        "skill.body",
        "knowledge_base.description",
        "connector.description",
        "bridge.notes",
        "user_group.description",
        "user_role.description",
    }
)

_TIMEOUT_SECONDS = 30.0


def _context_name(context: dict[str, Any] | None) -> str:
    if not context:
        return ""
    raw = context.get("name")
    if raw is None:
        return ""
    return str(raw).strip()


def _resolve_llm(server: Any, *, default_model: str | None) -> tuple[Any, str]:
    """Pick an LLM via explicit ref or automatic route (shared factory)."""
    if server.app_runtime is None:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "runtime unavailable")
    registry = server.app_runtime.agent_registry
    harness_manager = getattr(registry, "harness_manager", None)
    factory = getattr(harness_manager, "shared_factory", None) if harness_manager else None
    if factory is None:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "model factory unavailable")

    providers = registry.providers
    requested = (default_model or "").strip()
    model_ref: str | None = None
    if requested and requested.lower() != "auto" and providers.is_model_ref_usable(requested):
        model_ref = requested
    else:
        model_ref = registry.resolve_fallback_model_ref() or providers.resolve_first_model_ref()

    if not model_ref:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "no usable model for text assist")

    try:
        return factory.get(model_ref), model_ref
    except Exception as exc:
        logger.warning("text assist model unavailable ref=%s: %s", model_ref, exc)
        raise OctopError(ErrorCode.INTERNAL_ERROR, "model unavailable for text assist") from exc


def _build_messages(
    *,
    kind: str,
    text: str,
    name: str,
    locale: Locale,
) -> list[Any]:
    from langchain_core.messages import HumanMessage, SystemMessage  # noqa: PLC0415

    system = tr(f"text_assist.kinds.{kind}.system", locale)
    if kind == "chat.prompt":
        user = tr(f"text_assist.kinds.{kind}.user", locale, text=text)
    elif text:
        user = tr(
            f"text_assist.kinds.{kind}.user_polish",
            locale,
            name=name,
            text=text,
        )
    else:
        user = tr(f"text_assist.kinds.{kind}.user_generate", locale, name=name)
    return [SystemMessage(content=system), HumanMessage(content=user)]


async def run_text_assist(
    *,
    server: Any,
    kind: str,
    text: str = "",
    context: dict[str, Any] | None = None,
    locale: str | Locale = "en",
    default_model: str | None = None,
) -> str:
    """Polish or generate short copy for a known assist kind.

    ``chat.prompt`` requires non-empty ``text``. Form kinds require
    ``context.name``; ``text`` may be empty to generate from the name.
    Model selection uses an explicit usable ref when provided, otherwise
    the automatic route (``resolve_fallback_model_ref``).
    """
    if kind not in ASSIST_KINDS:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"unknown assist kind: {kind}")

    draft = (text or "").strip()
    name = _context_name(context)
    loc = normalize_locale(str(locale))

    if kind == "chat.prompt":
        if not draft:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "text is required")
    elif kind in _FORM_KINDS:
        if not name:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "context.name is required")
    else:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"unknown assist kind: {kind}")

    llm, model_ref = _resolve_llm(server, default_model=default_model)
    messages = _build_messages(kind=kind, text=draft, name=name, locale=loc)
    try:
        result = await ainvoke_text(llm, messages, timeout=_TIMEOUT_SECONDS)
    except TimeoutError:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "text assist timed out") from None
    except Exception:
        logger.exception("text assist failed kind=%s model=%s", kind, model_ref)
        raise OctopError(ErrorCode.INTERNAL_ERROR, "text assist failed") from None

    polished = (result or "").strip()
    if not polished:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "model returned empty text assist result")
    return polished
