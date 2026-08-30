"""Orchestrate HITL pause/resume for IM channels."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from harness_agent.slash import SlashCommand
from harness_gateway.models import MessageEvent

from octop.i18n.domains.slash import tr
from octop.infra.gateway.hitl.format import (
    extract_questions,
    format_ask_card,
    is_ask_action_requests,
    parse_action_requests,
    parse_ask_reply,
    parse_review_configs,
)
from octop.infra.gateway.hitl.store import HitlPendingRecord, HitlPendingStore
from octop.infra.gateway.process.usage_record import UsageTracker
from octop.infra.gateway.slash.ctx import ensure_thread_id
from octop.infra.gateway.slash.formatting import markdown_bullets
from octop.infra.utils.locale import Locale, normalize_locale

if TYPE_CHECKING:
    from octop.infra.agents.manager import AgentManager
    from octop.infra.gateway.slash.ctx import SlashCtx


@dataclass
class HitlStreamContext:
    thread_id: str
    agent_id: str
    user_id: int
    session_key: str
    channel_type: str


@dataclass
class HitlSlashOutcome:
    """Filled by :meth:`HitlChannelCoordinator.iter_slash_resolution` for the caller."""

    completed_turn: bool = False


@dataclass
class HitlAnswerOutcome:
    """Whether an IM answer resumed the graph or only advanced the form."""

    completed_turn: bool = False
    awaiting_more: bool = False


def pending_hitl_payload(
    store: HitlPendingStore,
    *,
    thread_id: str,
    agent_id: str,
    user_id: int,
) -> dict[str, Any] | None:
    record = store.resolve_pending_for_thread(
        thread_id,
        agent_id=agent_id,
        user_id=user_id,
    )
    if record is None:
        return None
    return {
        "pending_id": record.pending_id,
        "action_requests": record.action_requests,
        "review_configs": record.review_configs,
    }


def decision_rejection_reason(
    record: HitlPendingRecord,
    decisions: list[dict[str, Any]],
) -> str | None:
    """Check decisions against the pause's ``allowed_decisions``.

    The agent middleware raises deep inside the graph when a decision type is
    not allowed for its tool, which surfaces to the user as an opaque "model
    retry failed". Catching it at the API boundary turns a stale or buggy client
    into an actionable 400 instead.

    Returns an error message, or ``None`` when the decisions are acceptable.
    """
    actions = record.action_requests
    if len(decisions) != len(actions):
        return f"expected {len(actions)} decision(s) for this pause, got {len(decisions)}"
    allowed_by_action: dict[str, set[str]] = {}
    for config in record.review_configs or []:
        name = config.get("action_name")
        allowed = config.get("allowed_decisions")
        if isinstance(name, str) and isinstance(allowed, list):
            allowed_by_action[name] = {str(item) for item in allowed}
    for action, decision in zip(actions, decisions, strict=True):
        allowed = allowed_by_action.get(str(action.get("name")))
        if not allowed:
            continue
        kind = str(decision.get("type"))
        if kind not in allowed:
            return (
                f"decision '{kind}' is not allowed for tool "
                f"'{action.get('name')}' (allowed: {', '.join(sorted(allowed))})"
            )
    return None


class HitlChannelCoordinator:
    def __init__(self, store: HitlPendingStore | None = None) -> None:
        self._store = store or HitlPendingStore()

    @property
    def store(self) -> HitlPendingStore:
        return self._store

    def register_from_request(
        self,
        raw_request: dict[str, Any],
        *,
        ctx: HitlStreamContext,
    ) -> HitlPendingRecord:
        return self._store.register(
            thread_id=ctx.thread_id,
            agent_id=ctx.agent_id,
            user_id=ctx.user_id,
            session_key=ctx.session_key,
            channel_type=ctx.channel_type,
            action_requests=parse_action_requests(raw_request),
            review_configs=parse_review_configs(raw_request),
        )

    @staticmethod
    def build_decisions(
        action_requests: list[dict[str, Any]],
        *,
        approve: bool,
        message: str | None = None,
    ) -> list[dict[str, Any]]:
        count = len(action_requests) or 1
        if approve:
            return [{"type": "approve"} for _ in range(count)]
        reject_message = message or "Rejected by user"
        return [{"type": "reject", "message": reject_message} for _ in range(count)]

    def resolve_ask_pending(
        self,
        session_key: str,
        *,
        agent_id: str,
        user_id: int,
    ) -> HitlPendingRecord | None:
        """Return the open ``ask_user_question`` pause this user may answer.

        Returns ``None`` for approval pauses (those keep using ``/approve``) and
        for questions addressed to a different user in the same group chat.
        """
        record = self._store.resolve_for_session(session_key, agent_id=agent_id)
        if record is None or record.status != "pending":
            return None
        if record.user_id != user_id:
            return None
        if not is_ask_action_requests(record.action_requests):
            return None
        return record

    @staticmethod
    def build_answer_decisions(
        record: HitlPendingRecord,
        text: str,
        *,
        locale: str,
    ) -> list[dict[str, Any]]:
        """Build ``respond`` decisions carrying the user's answer to the model."""
        message = parse_ask_reply(
            text,
            extract_questions(record.action_requests),
            locale=locale,
        )
        count = len(record.action_requests) or 1
        return [{"type": "respond", "message": message} for _ in range(count)]

    @staticmethod
    def _answer_decisions(
        record: HitlPendingRecord,
        message: str,
    ) -> list[dict[str, Any]]:
        count = len(record.action_requests) or 1
        return [{"type": "respond", "message": message} for _ in range(count)]

    @staticmethod
    def _collected_answer_message(
        questions: list[dict[str, Any]],
        answers: list[str],
        *,
        locale: Locale,
    ) -> str:
        lines = [tr("ask.answered_prefix", locale).rstrip()]
        for index, answer in enumerate(answers):
            question = questions[index] if index < len(questions) else {}
            header = str(question.get("header") or "").strip()
            prompt = str(question.get("question") or "").strip()
            label = header or prompt or str(index + 1)
            lines.append(f"- {label}: {answer}")
        return "\n".join(lines)

    def collect_ask_reply(
        self,
        record: HitlPendingRecord,
        text: str,
        *,
        locale: str | Locale,
    ) -> tuple[str | None, str | None]:
        """Collect one IM answer; return ``(resume_message, next_card)``."""
        lang = normalize_locale(str(locale))
        questions = extract_questions(record.action_requests)
        if not questions:
            return parse_ask_reply(text, questions, locale=lang), None

        current = min(record.ask_question_index, len(questions) - 1)
        answer = parse_ask_reply(text, [questions[current]], locale=lang)
        prefix = tr("ask.answered_prefix", lang)
        if answer.startswith(prefix):
            answer = answer[len(prefix) :].strip()
        updated = self._store.append_ask_answer(record.pending_id, answer)
        if updated is None:
            return None, None

        if updated.ask_question_index < len(questions):
            next_card = format_ask_card(
                questions,
                pending_id=record.pending_id,
                locale=lang,
                question_index=updated.ask_question_index,
            )
            return None, next_card

        return (
            self._collected_answer_message(
                questions,
                updated.ask_answers,
                locale=lang,
            ),
            None,
        )

    async def iter_answer_resolution(
        self,
        record: HitlPendingRecord,
        text: str,
        *,
        agent_manager: AgentManager,
        locale: str,
        usage_tracker: UsageTracker | None = None,
        history_tracker: Any | None = None,
        projection_state: Any | None = None,
        outcome: HitlAnswerOutcome | None = None,
    ) -> AsyncIterator[MessageEvent]:
        """Collect one IM answer and resume only after the final question."""
        from octop.infra.gateway.process.stream_project import (
            StreamProjectionState,
            project_resume_stream,
        )

        lang = normalize_locale(locale)
        resume_message, next_card = self.collect_ask_reply(record, text, locale=lang)
        if next_card is not None:
            if outcome is not None:
                outcome.awaiting_more = True
            yield MessageEvent.text(f"{tr('ask.answer_recorded', lang)}\n\n{next_card}")
            return
        if resume_message is None:
            yield MessageEvent.error_event(tr("hitl.expired", lang))
            return

        yield MessageEvent.typing()
        decisions = self._answer_decisions(record, resume_message)
        hitl_ctx = HitlStreamContext(
            thread_id=record.thread_id,
            agent_id=record.agent_id,
            user_id=record.user_id,
            session_key=record.session_key,
            channel_type=record.channel_type,
        )
        state = projection_state if projection_state is not None else StreamProjectionState()
        # Resolve before streaming: a follow-up question registered mid-stream
        # must not be clobbered by a late mark_resolved on the old record.
        self._store.mark_resolved(record.pending_id, "approved")
        try:
            async for ev in project_resume_stream(
                agent_manager,
                record.agent_id,
                record.thread_id,
                decisions,
                usage_tracker=usage_tracker or UsageTracker(),
                history_tracker=history_tracker,
                locale=lang,
                projection_state=state,
                hitl_coordinator=self,
                hitl_ctx=hitl_ctx,
            ):
                yield ev
        except Exception as exc:
            yield MessageEvent.error_event(tr("hitl.resume_failed", lang, error=str(exc)))
            return
        if outcome is not None:
            outcome.completed_turn = True

    async def iter_slash_resolution(
        self,
        cmd: SlashCommand,
        ctx: SlashCtx,
        *,
        agent_manager: AgentManager,
        locale: str,
        usage_tracker: UsageTracker | None = None,
        outcome: HitlSlashOutcome | None = None,
    ) -> AsyncIterator[MessageEvent]:
        lang = normalize_locale(locale)
        if cmd.name == "pending":
            async for ev in self._iter_pending_list(ctx, lang):
                yield ev
            return

        yield MessageEvent.typing()

        approve = cmd.name == "approve"
        arg = cmd.args.strip()
        record = self._resolve_slash_record(ctx, approve=approve, arg=arg, lang=lang)
        if isinstance(record, MessageEvent):
            yield record
            return

        reject_message = None if approve else (arg or None)
        thread_id = record.thread_id if record is not None else await ensure_thread_id(ctx)
        action_requests = record.action_requests if record is not None else []
        decisions = self.build_decisions(
            action_requests,
            approve=approve,
            message=reject_message,
        )
        hitl_ctx = HitlStreamContext(
            thread_id=thread_id,
            agent_id=ctx.agent_id,
            user_id=ctx.user_id,
            session_key=ctx.session_key,
            channel_type=ctx.channel_type,
        )

        from octop.infra.gateway.process.stream_project import (
            StreamProjectionState,
            project_resume_stream,
        )

        tracker = usage_tracker or UsageTracker()
        projection_state = StreamProjectionState()
        had_output = False
        ack_sent = False
        resolved_status: Literal["approved", "rejected"] | None = (
            "approved" if approve else "rejected"
        )
        try:
            async for ev in project_resume_stream(
                agent_manager,
                ctx.agent_id,
                thread_id,
                decisions,
                usage_tracker=tracker,
                locale=lang,
                projection_state=projection_state,
                hitl_coordinator=self,
                hitl_ctx=hitl_ctx,
            ):
                if record is not None and not ack_sent:
                    ack = (
                        tr("hitl.approved_ack", lang) if approve else tr("hitl.rejected_ack", lang)
                    )
                    yield MessageEvent.text(ack)
                    ack_sent = True
                had_output = True
                yield ev
        except Exception as exc:
            if record is None and not had_output:
                yield MessageEvent.text(tr("hitl.none_pending", lang))
            else:
                yield MessageEvent.error_event(tr("hitl.resume_failed", lang, error=str(exc)))
            return

        if record is None and not had_output and not projection_state.hitl_paused:
            yield MessageEvent.text(tr("hitl.none_pending", lang))
            return

        if record is not None and not ack_sent:
            ack = tr("hitl.approved_ack", lang) if approve else tr("hitl.rejected_ack", lang)
            yield MessageEvent.text(ack)

        if record is not None and resolved_status is not None:
            self._store.mark_resolved(record.pending_id, resolved_status)

        if projection_state.hitl_paused:
            yield MessageEvent.text(tr("hitl.followup_pending", lang))

        if outcome is not None and (had_output or projection_state.hitl_paused):
            outcome.completed_turn = True

    def _resolve_slash_record(
        self,
        ctx: SlashCtx,
        *,
        approve: bool,
        arg: str,
        lang: Locale,
    ) -> HitlPendingRecord | MessageEvent | None:
        if approve and arg:
            record = self._store.get_pending(
                arg,
                session_key=ctx.session_key,
                agent_id=ctx.agent_id,
            )
            if record is None:
                return MessageEvent.text(tr("hitl.invalid_pending_id", lang, pending_id=arg))
            return record

        record = self._store.resolve_for_session(
            ctx.session_key,
            None,
            agent_id=ctx.agent_id,
        )
        if record is not None and record.user_id != ctx.user_id:
            return MessageEvent.text(tr("hitl.not_owner", lang))
        if record is not None and record.status == "expired":
            return MessageEvent.text(tr("hitl.expired", lang))
        return record

    async def _iter_pending_list(self, ctx: SlashCtx, lang: Locale) -> AsyncIterator[MessageEvent]:
        rows = self._store.list_pending_for_session(ctx.session_key, agent_id=ctx.agent_id)
        if not rows:
            yield MessageEvent.text(tr("hitl.pending_empty", lang))
            return
        bullets = [
            tr(
                "hitl.pending_line",
                lang,
                pending_id=row.pending_id,
                count=len(row.action_requests),
            )
            for row in rows
        ]
        yield MessageEvent.text(markdown_bullets(tr("hitl.pending_title", lang), bullets))
