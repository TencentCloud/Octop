"""Auto-tag threads from the chat topic after the first turn.

The caller decides *when* to tag (first successful turn); this module owns
*how*: pick a model, ask it to choose from the user's existing vocabulary,
and write the result without ever disturbing manually set tags.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable, Sequence

from octop.infra.agents.profile import parse_config_json
from octop.infra.agents.providers.probe import build_probe_chat_model
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.providers import ProviderRepo, ProviderRow
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.threads import ThreadRepo, parse_thread_tags
from octop.infra.utils.llm_text import llm_text_content

logger = logging.getLogger(__name__)

AUTO_THREAD_TAGS_KEY = "auto_thread_tags"

_MAX_TAGS = 3
_MAX_NEW_TAGS = 1
_TAG_TIMEOUT_S = 60.0
_MAX_SOURCE_CHARS = 500

_TAG_SPLIT_RE = re.compile(r"[、,，;；/\n]+")
_TAG_LEADING_ENUM_RE = re.compile(r"^[\d]+[.、)）\s]*")
_TAG_STRIP_CHARS = " \t\"'“”‘’、。."

_PROMPT = """你是一个对话分类助手。根据用户与 AI 助手对话的主题，为对话选择最贴切的标签。

对话标题：{title}
用户第一条消息：{message}

已有标签：{candidates}

要求：
1. 优先从"已有标签"中选择最贴切的；已有标签都不合适时才新增
2. 最多新增 1 个新标签，总共最多 3 个标签，每个标签不超过 6 个字
3. 只输出标签本身，用顿号（、）分隔，不要输出任何解释或其他内容"""


def split_llm_tags(text: str) -> list[str]:
    """Split raw LLM output into candidate tag strings (pre-sanitize)."""
    out: list[str] = []
    for piece in _TAG_SPLIT_RE.split(text):
        tag = _TAG_LEADING_ENUM_RE.sub("", piece.strip()).strip(_TAG_STRIP_CHARS)
        if tag:
            out.append(tag)
    return out


def enforce_tag_policy(
    tags: Sequence[str],
    candidates: Sequence[str],
    *,
    max_tags: int = _MAX_TAGS,
    max_new: int = _MAX_NEW_TAGS,
) -> list[str]:
    """Cap total tags and how many may fall outside the existing vocabulary."""
    known = set(candidates)
    out: list[str] = []
    new_count = 0
    for tag in tags:
        if not tag or tag in out:
            continue
        if tag not in known:
            if new_count >= max_new:
                continue
            new_count += 1
        out.append(tag)
        if len(out) >= max_tags:
            break
    return out


def build_auto_tag_prompt(*, title: str, message: str, candidates: Sequence[str]) -> str:
    source = message.strip()[:_MAX_SOURCE_CHARS]
    existing = "、".join(candidates) if candidates else "（无）"
    return _PROMPT.format(title=title.strip() or "（无）", message=source, candidates=existing)


class AutoTagger:
    """Assign tags to a thread based on its topic.

    Tags are written only when the thread has none, so manual edits always
    win. All failures are logged and swallowed: tagging must never break
    the message flow.
    """

    def __init__(
        self,
        thread_repo: ThreadRepo,
        agent_repo: AgentRepo,
        settings_repo: SettingsRepo,
        provider_repo: ProviderRepo,
        fallback_model_ref: Callable[[], str | None] | None = None,
    ) -> None:
        self._threads = thread_repo
        self._agents = agent_repo
        self._settings = settings_repo
        self._providers = provider_repo
        self._fallback_model_ref = fallback_model_ref

    def enabled(self, agent_id: str) -> bool:
        row = self._agents.get(agent_id)
        return (
            row is not None and parse_config_json(row.config_json).get(AUTO_THREAD_TAGS_KEY) is True
        )

    async def maybe_tag_thread(
        self,
        *,
        agent_id: str,
        user_id: int,
        thread_id: str,
        title: str,
        first_message: str,
    ) -> None:
        try:
            await self._tag_thread(
                agent_id=agent_id,
                user_id=user_id,
                thread_id=thread_id,
                title=title,
                first_message=first_message,
            )
        except Exception:
            logger.info("auto-tag failed for thread %s", thread_id, exc_info=True)

    async def _tag_thread(
        self,
        *,
        agent_id: str,
        user_id: int,
        thread_id: str,
        title: str,
        first_message: str,
    ) -> None:
        if not self.enabled(agent_id):
            logger.info("auto-tag skipped for thread %s: disabled", thread_id)
            return
        if self._has_tags(thread_id):
            logger.info("auto-tag skipped for thread %s: already tagged", thread_id)
            return
        resolved = self._resolve_model(thread_id)
        if resolved is None:
            logger.info("auto-tag skipped for thread %s: no usable model", thread_id)
            return
        provider, model_id = resolved
        candidates = self._threads.list_tags(agent_id=agent_id, user_id=user_id)
        chat = build_probe_chat_model(provider, model_id=model_id)
        prompt = build_auto_tag_prompt(title=title, message=first_message, candidates=candidates)
        result = await asyncio.wait_for(chat.ainvoke(prompt), timeout=_TAG_TIMEOUT_S)
        tags = enforce_tag_policy(
            parse_thread_tags(split_llm_tags(llm_text_content(result))), candidates
        )
        if not tags:
            logger.info("auto-tag skipped for thread %s: model returned no tags", thread_id)
            return
        if self._has_tags(thread_id):
            logger.info("auto-tag skipped for thread %s: tags set while waiting", thread_id)
            return
        self._threads.set_tags(thread_id, tags)
        logger.info("auto-tagged thread %s: %s", thread_id, ", ".join(tags))

    def _resolve_model(self, thread_id: str) -> tuple[ProviderRow, str | None] | None:
        """Walk the same fallback chain chat uses to pick a model.

        Global active model first, then the thread's own model_ref, then an
        optional last-resort callback (the gateway injects the agent
        manager's "first enabled catalog model" fallback).
        """
        name, model_id = self._settings.get_active_model()
        if name:
            provider = self._providers.get_by_name(name)
            if provider is not None:
                return provider, model_id or None
            logger.info("auto-tag: settings model provider %r missing, falling back", name)
        row = self._threads.get(thread_id)
        ref = (row.model_ref if row is not None else None) or ""
        if ref:
            resolved = self._ref_provider(ref)
            if resolved is not None:
                return resolved
            logger.info("auto-tag: thread model_ref %r unusable, falling back", ref)
        if self._fallback_model_ref is not None:
            fallback = self._fallback_model_ref()
            if fallback:
                resolved = self._ref_provider(fallback)
                if resolved is not None:
                    return resolved
        return None

    def _ref_provider(self, ref: str) -> tuple[ProviderRow, str | None] | None:
        name, _, model_id = ref.partition("/")
        if not name:
            return None
        provider = self._providers.get_by_name(name)
        if provider is None:
            return None
        return provider, model_id or None

    def _has_tags(self, thread_id: str) -> bool:
        row = self._threads.get(thread_id)
        if row is None:
            return True
        return bool(row.tags)
