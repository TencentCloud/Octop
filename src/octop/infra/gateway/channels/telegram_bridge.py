"""Host-owned Telegram choices; Gateway owns transport and callback identity checks."""

from __future__ import annotations

import asyncio
import logging
import re
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

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.hitl.format import extract_questions
from octop.infra.gateway.process.message_keys import (
    resolve_user_id_for_message,
    session_key_from_message,
)
from octop.infra.gateway.slash.parser import parse_slash
from octop.infra.utils.stream_close import close_event_stream

logger = logging.getLogger(__name__)


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
            if not self._button_is_current(msg):
                return
            if msg.button_state.model_page is not None:
                if msg.channel_subject is not None:
                    await self._send_models(msg, msg.channel_subject, msg.button_state.model_page)
                return
            msg = InboundMessage(**msg.model_dump(exclude={"button_state"}))
        # Gateway has already checked that an addressed command names this bot.
        text = re.sub(r"^(\s*/[\w-]+)@[\w]+(?=\s|$)", r"\1", msg.text)
        if text != msg.text:
            msg = msg.model_copy(
                update={
                    "content": [
                        TextContent(text=re.sub(r"^(\s*/[\w-]+)@[\w]+(?=\s|$)", r"\1", part.text))
                        if isinstance(part, TextContent)
                        else part
                        for part in msg.content
                    ]
                }
            )
        agent_id = msg.tenant_id or ""
        session_key = session_key_from_message(msg, agent_id=agent_id)
        pending_id = None
        failed = False
        stream = self.processor(msg)
        try:
            async for event in stream:
                failed = failed or event.type == MessageEventType.ERROR
                pending_id = event.metadata.get("octop_hitl_pending_id") or pending_id
                if event.type == MessageEventType.COMPLETED and not failed:
                    await self._send_choices(msg, session_key, pending_id)
                yield event
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
    ) -> None:
        agent_id = msg.tenant_id or ""
        manager = self.gateway.channel_manager
        channel = manager.get_channel(self.channel_id) if manager else None
        if channel is None or not callable(getattr(channel, "send_buttons", None)):
            return
        if not callable(getattr(manager, "run_in_session", None)):
            return
        subject = msg.channel_subject
        if subject is None or not msg.metadata.get("user_id"):
            return
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
                return
            question = questions[index]
            # Multi-select continues to use the existing text answer parser.
            if question.get("multiSelect") or question.get("multi_select"):
                return
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
                return
            if owner is None:
                return
            await self._send_models(msg, subject)
            return
        if actions:
            await channel.send_buttons(subject, text, actions)

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
            await channel.send_buttons(subject, f"/model ({page + 1})", actions)

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

    def _button_is_current(self, msg: _ButtonReply) -> bool:
        state = msg.button_state
        agent_id = msg.tenant_id or ""
        session_key = session_key_from_message(msg, agent_id=agent_id)
        reason = self._button_reject_reason(msg, state, agent_id, session_key)
        if reason is not None:
            # 按钮点击被静默丢弃是"点击没反应"的直接表现，必须留下线索。
            logger.warning(
                "telegram button reply dropped: agent=%s session=%s reason=%s text=%r",
                agent_id,
                session_key,
                reason,
                state.text,
            )
            return False
        return True

    def _button_reject_reason(
        self, msg: _ButtonReply, state: _ButtonState, agent_id: str, session_key: str
    ) -> str | None:
        current_owner = self.gateway._repos.agent_repo.get(agent_id)
        if current_owner is None or current_owner.user_id != state.owner_id:
            return "owner_changed"
        if self.gateway.thread_registry.get_bound_thread_id(session_key) != state.thread_id:
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
                self.gateway.thread_registry.get_bound_thread_id(record.session_key)
                != record.thread_id
            ):
                return "record_thread_rebound"
        return None
