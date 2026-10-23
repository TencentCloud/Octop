"""Host-owned Telegram choices; Gateway owns transport and callback identity checks."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, fields
from typing import Any

from octop_gateway.models import (
    ChannelSubject,
    InboundMessage,
    MessageEvent,
    MessageEventType,
    TextContent,
)

from octop.i18n.domains.channel import telegram_reject_notice
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.hitl.format import extract_questions
from octop.infra.gateway.process.message_keys import (
    resolve_user_id_for_message,
    session_key_from_message,
)
from octop.infra.gateway.slash.parser import parse_slash
from octop.infra.utils.locale import Locale, resolve_user_locale
from octop.infra.utils.stream_close import close_event_stream

logger = logging.getLogger(__name__)

# HITL pending 记录存活 30 分钟，按钮回调不能比它先过期（gateway 默认 300s）。
_BUTTON_TTL = 1800.0


def validate_telegram_config(kind: str, config: dict[str, Any]) -> None:
    """Reject options silently ignored by an older installed Gateway."""
    if kind != "telegram":
        return
    from octop_gateway.channels.telegram import TelegramConfig

    supported = {item.name for item in fields(TelegramConfig)}
    # These options belong to Octop rather than TelegramConfig.
    unsupported = set(config) - supported - {"response_mode", "enabled"}
    if unsupported:
        raise OctopError(
            ErrorCode.CHANNEL_OPTIONS_UNSUPPORTED,
            "Installed octop-gateway does not support Telegram options: "
            + ", ".join(sorted(unsupported))
            + ". Install a Gateway build supporting these options before saving.",
            details={"unsupported_options": sorted(unsupported)},
        )
    try:
        for item in fields(TelegramConfig):
            if (
                isinstance(item.default, bool)
                and item.name in config
                and not isinstance(config[item.name], bool)
            ):
                raise ValueError(f"Telegram {item.name} must be a boolean")
        factory = getattr(TelegramConfig, "from_dict", None)
        if callable(factory):
            factory(config)
        else:
            TelegramConfig(**{key: value for key, value in config.items() if key in supported})
    except (TypeError, ValueError) as exc:
        raise OctopError(ErrorCode.CHANNEL_INVALID_CREDENTIALS, str(exc)) from exc


@dataclass(frozen=True)
class _ButtonState:
    owner_id: int | None
    thread_id: str | None
    pending_id: str | None
    question_index: int
    model_page: int | None
    text: str


class _ButtonReply(InboundMessage):
    """Host-created queue item; platform dictionaries cannot construct this type."""

    button_state: _ButtonState


def _is_ask_card(event: MessageEvent) -> bool:
    """HITL card text in this event lists the same options the buttons offer.

    Telegram renders those options natively, so the card is only a fallback
    for channels without button support or when sending buttons fails.
    """
    return event.type == MessageEventType.MESSAGE and bool(
        event.metadata.get("octop_hitl_pending_id")
    )


def is_telegram_button_reply(msg: InboundMessage) -> bool:
    """Keep trusted button replies out of manager-level text batching."""
    return isinstance(msg, _ButtonReply)


class TelegramBridge:
    def __init__(self, gateway: Any, processor: Any, channel_id: str) -> None:
        self.gateway = gateway
        self.processor = processor
        self.channel_id = channel_id

    async def __call__(self, msg: InboundMessage) -> AsyncIterator[MessageEvent]:
        if isinstance(msg, _ButtonReply):
            # The normal worker holds the session lock for validation and execution.
            reason = self._button_reject_reason_call(msg)
            if reason is not None:
                await self._notify_button_rejected(msg, reason)
                return
            if msg.button_state.model_page is not None:
                if msg.channel_subject is not None:
                    await self._send_models(msg, msg.channel_subject, msg.button_state.model_page)
                return
            msg = InboundMessage(**msg.model_dump(exclude={"button_state"}))

        agent_id = msg.tenant_id or ""
        session_key = session_key_from_message(msg, agent_id=agent_id)
        pending_id = None
        failed = False
        # 问询卡片先扣住：Telegram 有原生按钮时只发按钮版，文本卡片会重复。
        held_card = None
        stream = self.processor(msg)
        try:
            async for event in stream:
                failed = failed or event.type == MessageEventType.ERROR
                event_pending = event.metadata.get("octop_hitl_pending_id")
                if not failed and event_pending:
                    pending_id = event_pending
                    if _is_ask_card(event):
                        held_card = event
                        continue
                if event.type == MessageEventType.COMPLETED and not failed:
                    if held_card is not None:
                        try:
                            sent = await self._send_choices(msg, session_key, pending_id)
                        except Exception:  # noqa: BLE001 按钮发送失败时文本卡片是唯一入口
                            logger.warning("telegram choice buttons failed; using text card")
                            sent = False
                        if not sent:
                            yield held_card
                        held_card = None
                    else:
                        await self._send_choices(msg, session_key, pending_id)
                elif held_card is not None and event.type in (
                    MessageEventType.ERROR,
                    MessageEventType.MESSAGE,
                ):
                    yield held_card
                    held_card = None
                yield event
            if held_card is not None:
                yield held_card
        except asyncio.CancelledError:
            # Harness execution can outlive consumption of its stream iterator.
            thread_id = self.gateway.thread_registry.get_bound_thread_id(session_key)
            if thread_id:
                self.gateway._agent_manager.cancel_stream(agent_id, thread_id)
            raise
        finally:
            # GeneratorExit 穿过 async-for 不会关闭内层生成器；不显式关闭
            # 会让整条 processor 链交给 GC 在异源 Context 里清理（曾致
            # ContextVar reset 崩溃、resume 中途丢失）。
            await close_event_stream(stream)

    async def _send_choices(
        self, msg: InboundMessage, session_key: str, pending_id: str | None
    ) -> bool:
        """Render pending choices as native buttons; False when text must carry them."""
        agent_id = msg.tenant_id or ""
        manager = self.gateway.channel_manager
        channel = manager.get_channel(self.channel_id) if manager else None
        if channel is None or not callable(getattr(channel, "send_buttons", None)):
            return False
        subject = msg.channel_subject
        if subject is None or not msg.metadata.get("user_id"):
            return False
        subject = ChannelSubject(
            subject_id=subject.subject_id,
            display_name=subject.display_name,
            chat_type=subject.chat_type,
            metadata={**subject.metadata, **msg.metadata},
        )
        owner = self.gateway._repos.agent_repo.get(agent_id)
        user_id = resolve_user_id_for_message(msg, agent_owner_id=owner.user_id if owner else None)
        hitl = self.gateway.processor.hitl_coordinator
        record = hitl.resolve_ask_pending(session_key, agent_id=agent_id, user_id=user_id)
        actions = []
        text = ""
        if record is not None and record.pending_id == pending_id:
            questions = extract_questions(record.action_requests)
            index = record.ask_question_index
            if index >= len(questions):
                return False
            question = questions[index]
            # Multi-select continues to use the existing text answer parser.
            if question.get("multiSelect") or question.get("multi_select"):
                return False
            text = str(question.get("question") or question.get("header") or "?")
            for number, option in enumerate(question.get("options") or [], start=1):
                if isinstance(option, dict) and option.get("label"):
                    actions.append(
                        (
                            str(option["label"]),
                            self._action(msg, subject, str(number), record.pending_id, index),
                        )
                    )
        else:
            cmd = parse_slash(msg.text)
            if cmd is None or cmd.name not in ("model", "models") or cmd.args.strip():
                return False
            if owner is None:
                return False
            await self._send_models(msg, subject)
            return False
        if actions:
            await channel.send_buttons(subject, text, actions, ttl=_BUTTON_TTL)
            return True
        return False

    def _locale(self, msg: InboundMessage) -> Locale:
        """Per-user locale for host-generated copy (stored preference, then channel hint)."""
        agent_id = msg.tenant_id or ""
        owner = self.gateway._repos.agent_repo.get(agent_id)
        user_id = resolve_user_id_for_message(
            msg, agent_owner_id=owner.user_id if owner is not None else None
        )
        return resolve_user_locale(
            user_repo=getattr(self.gateway._repos, "user_repo", None),
            user_id=user_id if isinstance(user_id, int) else 0,
            channel_type=msg.channel_type or "telegram",
            metadata=msg.metadata,
        )

    async def _notify_button_rejected(self, msg: _ButtonReply, reason: str) -> None:
        """按钮失效不再静默：按 reason 给一句短提示。

        gateway 已在 invoke 前应答过 callback query，无法再用 toast，只能发一条消息。
        不先发 typing：单 chat 1 req/s 限流下它只会拖慢提示本身。
        """
        manager = self.gateway.channel_manager
        channel = manager.get_channel(self.channel_id) if manager else None
        subject = msg.channel_subject
        if channel is None or subject is None:
            return
        send_text = getattr(channel, "push_text", None)
        if callable(send_text):
            try:
                await send_text(subject, telegram_reject_notice(reason, self._locale(msg)))
            except Exception:  # noqa: BLE001 反馈失败不应再抛
                logger.warning("reject notice send failed reason=%s", reason)

    def _model_refs(self) -> list[str]:
        from octop.infra.agents.providers.store import enabled_model_refs

        refs: set[str] = set()
        for provider in self.gateway._repos.provider_repo.list_all():
            if provider.enabled:
                refs.update(
                    enabled_model_refs(
                        provider.name, provider.get_models(), provider_api_key=provider.api_key
                    )
                )
        return sorted(refs)

    async def _send_models(
        self, msg: InboundMessage, subject: ChannelSubject, page: int = 0
    ) -> None:
        manager = self.gateway.channel_manager
        channel = manager.get_channel(self.channel_id) if manager else None
        if channel is None:
            return
        refs = self._model_refs()
        size = 48  # Leave room for both navigation actions within 50 buttons.
        page = min(page, max(0, (len(refs) - 1) // size))
        actions = [
            (ref, self._action(msg, subject, f"/model {ref}"))
            for ref in refs[page * size : (page + 1) * size]
        ]
        for target, label in ((page - 1, "←"), (page + 1, "→")):
            if target >= 0 and target * size < len(refs):
                actions.append((label, self._action(msg, subject, "", model_page=target)))
        if actions:
            await channel.send_buttons(subject, f"/model ({page + 1})", actions, ttl=_BUTTON_TTL)

    def _action(
        self,
        msg: InboundMessage,
        subject: ChannelSubject,
        text: str,
        pending_id: str | None = None,
        question_index: int = 0,
        model_page: int | None = None,
    ) -> Callable[[], Awaitable[None]]:
        agent_id = msg.tenant_id or ""
        session_key = session_key_from_message(msg, agent_id=agent_id)
        thread_id = self.gateway.thread_registry.get_bound_thread_id(session_key)
        owner = self.gateway._repos.agent_repo.get(agent_id)
        owner_id = owner.user_id if owner else None

        state = _ButtonState(owner_id, thread_id, pending_id, question_index, model_page, text)

        async def action() -> None:
            manager = self.gateway.channel_manager
            channel = manager.get_channel(self.channel_id) if manager else None
            if channel is None:
                return
            reply = _ButtonReply(
                **{
                    **msg.model_dump(exclude={"button_state"}),
                    "content": [TextContent(text=text)],
                    "channel_subject": subject,
                },
                button_state=state,
            )
            channel.enqueue(reply)

        return action

    def _button_reject_reason_call(self, msg: _ButtonReply) -> str | None:
        state = msg.button_state
        agent_id = msg.tenant_id or ""
        session_key = session_key_from_message(msg, agent_id=agent_id)
        reason = self._button_reject_reason(msg, state, agent_id, session_key)
        if reason is not None:
            # 按钮点击被丢弃必须留下线索，同时把 reason 交给上层做用户反馈。
            logger.warning(
                "telegram button reply dropped: agent=%s session=%s reason=%s text=%r",
                agent_id,
                session_key,
                reason,
                state.text,
            )
        return reason

    def _button_reject_reason(
        self, msg: _ButtonReply, state: _ButtonState, agent_id: str, session_key: str
    ) -> str | None:
        current_owner = self.gateway._repos.agent_repo.get(agent_id)
        if current_owner is None or current_owner.user_id != state.owner_id:
            return "owner_changed"
        # 群聊里任何人的新消息都会重绑 thread，thread 硬校验会让仍然有效的按钮在几秒内
        # 失效（点击后毫无反应）；此时归属由 gateway 的 user+chat 校验、owner/model 校验
        # 以及 HITL 的 session+user+question index 兜住。私聊保持 thread 严格校验。
        strict_thread = not msg.metadata.get("is_group")
        if (
            strict_thread
            and self.gateway.thread_registry.get_bound_thread_id(session_key) != state.thread_id
        ):
            return "thread_rebound"
        if (
            state.text.startswith("/model ")
            and state.text.removeprefix("/model ") not in self._model_refs()
        ):
            return "model_unavailable"
        if state.pending_id is not None:
            record = self.gateway.processor.hitl_coordinator.store.get_pending(
                state.pending_id, session_key=session_key, agent_id=agent_id
            )
            if record is None:
                return "pending_expired_or_resolved"
            if record.ask_question_index != state.question_index:
                return "question_index_changed"
            if record.user_id != resolve_user_id_for_message(msg, agent_owner_id=state.owner_id):
                return "user_mismatch"
            if (
                strict_thread
                and self.gateway.thread_registry.get_bound_thread_id(record.session_key)
                != record.thread_id
            ):
                return "thread_rebound"
        return None
