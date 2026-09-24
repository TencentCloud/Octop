"""Team room: dispatch members, relay live chunks, project history.

A team host is a wrapped expert. Members stay regular experts and are
reached with ``ask_agent``. This class owns the room side of that call:

- live tokens go to the team page and the member page over WebSocket
- history for the team page is a ``thread_messages`` row (not the host checkpoint)
- the member page uses the member's own thread / checkpoint
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from collections.abc import Callable
from dataclasses import fields
from typing import TYPE_CHECKING, Any

from harness_agent.messages import extract_call_response
from harness_agent.teams.inbox import InboxMessage
from harness_agent.teams.processor import ReplyEvent
from harness_agent.teams.util import (
    PeerCall,
    PeerSession,
    build_one_shot_request,
    derive_peer_thread_id,
)
from langchain_core.messages import AIMessage, HumanMessage

from octop.i18n import tr
from octop.infra.agents.teams.service import is_team_agent
from octop.infra.gateway.process.history_projection import (
    live_message_inputs,
    message_inputs,
)
from octop.infra.utils.locale import DEFAULT_LOCALE, resolve_user_locale
from octop.infra.utils.ulid import new_ulid

if TYPE_CHECKING:
    from octop.infra.agents.manager import AgentManager
    from octop.infra.db.repos.sessions import SessionRow
    from octop.infra.db.repos.users import UserRepo
    from octop.infra.gateway.threads import ThreadRegistry

logger = logging.getLogger(__name__)

_ROOM_HISTORY_LIMIT = 40
_HOST_IDLE_POLL_SEC = 0.05
_HOST_IDLE_WAIT_SEC = 45.0
_RELAY_CHUNK_TYPES = frozenset(
    {"token", "reasoning", "tool_call_chunk", "tool_result", "error", "attachment"}
)
_STREAM_SPEAKER_TYPES = frozenset(
    {
        "token",
        "reasoning",
        "tool_call_chunk",
        "tool_result",
        "error",
        "attachment",
        "slash_action",
        "done",
    }
)


def host_system_prompt(row: Any, user_repo: Any) -> str:
    """Runtime host briefing, appended to any custom ``system_prompt``."""
    uid = getattr(row, "user_id", None)
    locale = (
        resolve_user_locale(user_repo=user_repo, user_id=uid)
        if isinstance(uid, int) and uid > 0
        else DEFAULT_LOCALE
    )
    briefing = tr("teams.host_briefing", locale)
    custom = str(getattr(row, "system_prompt", None) or "").strip()
    return f"{custom}\n\n{briefing}".strip() if custom else briefing


class TeamManager:
    """Octop-side team room. Harness still owns ``ask_agent`` / inbox."""

    def __init__(
        self,
        *,
        agent_manager: AgentManager,
        thread_registry: ThreadRegistry,
        user_repo: UserRepo,
        thread_message_repo: Any | None = None,
        gateway: Any | None = None,
    ) -> None:
        self._agent_manager = agent_manager
        self._thread_registry = thread_registry
        self._user_repo = user_repo
        self._thread_message_repo = thread_message_repo
        self._gateway = gateway
        self._peer_prompts: dict[tuple[str, str], tuple[str, str]] = {}
        self._live_host_replies: set[str] = set()

    def replace_thread_message_repo(self, repo: Any) -> None:
        self._thread_message_repo = repo

    # -- ask_agent session (member page) -------------------------------------

    async def prepare_peer_session(self, call: PeerCall) -> PeerSession | None:
        """Open the member thread and stash the host's rewritten assignment."""
        thread_id = (
            derive_peer_thread_id(call.source_thread_id, call.to_agent_id)
            if call.source_thread_id
            else None
        )
        session_key = None
        uid = _octop_user_id(call.user_id)
        group = self._is_group_dispatch(call)
        extra = self._member_runtime(call)
        question = ""
        dispatch_message = None
        if group:
            question = await self._assignment_text(call)
            dispatch_message = await self._dispatch_message(call, uid)
            if thread_id and (question or dispatch_message):
                self.stash_peer_prompt(
                    call.to_agent_id,
                    thread_id,
                    question=question or str(dispatch_message or ""),
                    dispatch=dispatch_message or question,
                )
        # Expert-to-expert sync ask_agent also uses peer:{room} so it does not
        # reuse the callee's 1:1 DM. Existing DM peer history will not follow.
        if call.source_session_key:
            if call.source_thread_id:
                session_key = self._thread_registry.peer_room_session_key(
                    call.source_session_key,
                    call.to_agent_id,
                    room_thread_id=call.source_thread_id,
                    group=group,
                )
            else:
                session_key = self._thread_registry.peer_session_key(
                    call.source_session_key, call.to_agent_id
                )
        self._track_job(call, begin=True)
        if thread_id and session_key and uid is not None:
            parts = session_key.split(":", 3)
            channel_type = parts[1] if len(parts) >= 2 else "dashboard"
            self._thread_registry.ensure_thread(
                thread_id=thread_id,
                agent_id=call.to_agent_id,
                user_id=uid,
                channel_type=channel_type,
                session_key=session_key,
            )
            self._title_member_thread(call, thread_id, uid)
            if group:
                self._seed_member_user_question(
                    thread_id,
                    question or str(call.message or ""),
                    turn_id=getattr(call, "job_id", None),
                )
        return _make_peer_session(
            thread_id=thread_id,
            session_key=session_key,
            configurable=extra,
            message=question or dispatch_message,
        )

    async def record_peer_turn(
        self,
        call: PeerCall,
        thread_id: str,
        result: dict[str, Any],
    ) -> None:
        """Write the callee page, then copy the final answer onto the room if async."""
        try:
            if not thread_id:
                return
            self._touch_thread(thread_id, call.message)
            if self._thread_message_repo is None:
                return
            messages = result.get("messages")
            visible = _peer_turn_messages(messages) if isinstance(messages, list) else []
            visible = [msg for msg in visible if _message_role(msg) not in {"human", "user"}]
            prompt = await self._assignment_text(call)
            if prompt:
                visible = [
                    HumanMessage(
                        content=prompt,
                        id=_peer_user_message_id(thread_id, getattr(call, "job_id", None)),
                    ),
                    *visible,
                ]
            if not visible:
                return
            self._ensure_projection(thread_id)
            try:
                self._thread_message_repo.append_if_ready(
                    thread_id,
                    message_inputs(visible, dedupe_missing_ids=True),
                )
            except Exception:
                logger.warning(
                    "failed to append peer history projection for thread=%s",
                    thread_id,
                    exc_info=True,
                )
            await self.fan_in_peer_turn(
                call,
                messages if isinstance(messages, list) else [],
                live_streamed=bool(result.get("team_live_streamed")),
            )
        finally:
            self._track_job(call, begin=False)

    def compose_followup(
        self,
        msg: InboxMessage,
        *,
        result_text: str | None,
        error_text: str | None,
    ) -> str:
        _ = result_text
        child_name = self._display_name(msg.target_agent_id)
        locale = self._locale_for(_octop_user_id(msg.user_id))
        if error_text:
            return tr(
                "teams.followup_failed",
                locale,
                name=child_name,
                task=msg.message,
                error=error_text,
            )
        return tr(
            "teams.followup_done",
            locale,
            name=child_name,
            task=msg.message,
        )

    async def on_reply(self, event: ReplyEvent) -> None:
        self._end_job_from_reply(event)
        room = str(event.source_thread_id or "").strip()
        speaker = event.source_agent_id
        text = (
            event.error_text or "Background task did not complete."
            if event.status != "done"
            else (event.reply_text or "(empty)")
        )
        if room:
            await self._push_room_to_channels(room, speaker, text, prefix_speaker=False)
        live_ws = self._take_live_host_reply(room) and event.status == "done"
        if live_ws:
            if room:
                self._thread_registry.touch_last_active(room)
            return
        session_key = event.metadata.get("session_key")
        session = (
            self._thread_registry.get_session(session_key.strip())
            if isinstance(session_key, str) and session_key.strip()
            else None
        )
        if session is not None and not self._thread_registry.is_im_session(session):
            await self._deliver_text(
                session,
                str(session.session_key),
                text,
                speaker_id=speaker,
            )
            return
        if session is not None:
            return
        if room:
            await self._publish_room_text(room, speaker, text)
            self._thread_registry.touch_last_active(room)
            return
        logger.warning("team reply %s: no room to publish", event.inbox_id)

    # -- live room + member page ---------------------------------------------

    async def stream_peer_to_room(
        self,
        request: Any,
        *,
        room_thread_id: str,
        speaker_id: str,
        extra_stamp: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run the member turn and fan tokens to both chat pages."""
        payload = _chat_request_payload(request, speaker_id)
        member_tid = str(payload.get("thread_id") or "").strip()
        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        relayed_visible = False
        try:
            async for chunk in self._agent_manager.stream(speaker_id, payload):
                if not isinstance(chunk, dict):
                    continue
                kind = str(chunk.get("type") or "")
                if kind == "token":
                    piece = str(chunk.get("content") or "")
                    if piece:
                        text_parts.append(piece)
                elif kind == "reasoning":
                    piece = str(chunk.get("content") or "")
                    if piece:
                        reasoning_parts.append(piece)
                if kind in _RELAY_CHUNK_TYPES:
                    if kind in {"token", "reasoning", "attachment"} and self._thread_is_watched(
                        room_thread_id
                    ):
                        relayed_visible = True
                    relay = chunk
                    if extra_stamp and kind in {"token", "reasoning"}:
                        relay = {**chunk, **extra_stamp}
                    await self._relay_chunk(
                        relay,
                        room_thread_id=room_thread_id,
                        member_thread_id=member_tid,
                        speaker_id=speaker_id,
                    )
        except Exception:
            logger.warning(
                "team peer stream failed speaker=%s room=%s",
                speaker_id,
                room_thread_id,
                exc_info=True,
            )
            raise
        finally:
            done: dict[str, Any] = {"type": "done"}
            if extra_stamp:
                done = {**done, **extra_stamp}
            await self._relay_chunk(
                done,
                room_thread_id=room_thread_id,
                member_thread_id=member_tid,
                speaker_id=speaker_id,
            )
        stream_text = "".join(text_parts).strip()
        return {
            "messages": await self._peer_result_messages(
                speaker_id,
                member_tid,
                text_parts,
                reasoning_parts,
            ),
            "team_live_streamed": relayed_visible,
            "stream_text": stream_text,
        }

    async def _wait_host_dispatch_idle(self, host_id: str, room_thread_id: str) -> None:
        """Do not start wrap-up while the first host turn is still streaming.

        Member answers can finish while the host is still saying「稍候」.
        Two host token streams on the same room socket then interleave.
        """
        hub = getattr(self._gateway, "ws_hub", None) if self._gateway is not None else None
        check_turn = getattr(hub, "is_turn_active", None)
        check_host = getattr(self._agent_manager, "is_agent_active", None)
        deadline = asyncio.get_running_loop().time() + _HOST_IDLE_WAIT_SEC
        while True:
            turn_active = check_turn(room_thread_id) is True if callable(check_turn) else False
            host_busy = check_host(host_id) is True if callable(check_host) else False
            if not turn_active and not host_busy:
                return
            if asyncio.get_running_loop().time() >= deadline:
                logger.warning(
                    "team wrap-up waited %.0fs for host idle host=%s room=%s",
                    _HOST_IDLE_WAIT_SEC,
                    host_id,
                    room_thread_id,
                )
                return
            await asyncio.sleep(_HOST_IDLE_POLL_SEC)

    async def stream_host_followup_to_room(
        self,
        request: Any,
        *,
        room_thread_id: str,
        speaker_id: str,
    ) -> dict[str, Any]:
        """Stream the host wrap-up onto the team page (inbox wakeup)."""
        await self._wait_host_dispatch_idle(speaker_id, room_thread_id)
        payload = _chat_request_payload(request, speaker_id)
        payload["thread_id"] = room_thread_id
        result = await self.stream_peer_to_room(
            payload,
            room_thread_id=room_thread_id,
            speaker_id=speaker_id,
            extra_stamp={"team_wrapup": True},
        )
        text = str(result.get("stream_text") or "").strip()
        if not text:
            for msg in reversed(result.get("messages") or []):
                text = _assistant_text(msg)
                if text:
                    break
        if text:
            self._persist_room_assistant(room_thread_id, speaker_id, text, wrapup=True)
        live = bool(result.get("team_live_streamed"))
        # Some models finish wrap-up in checkpoint/values only — no token
        # frames. Push the final text so the open room still sees it.
        if text and not live:
            await self._push_room_snapshot(
                room_thread_id,
                speaker_id,
                text,
                wrapup=True,
            )
            live = self._thread_is_watched(room_thread_id)
        if room_thread_id and text and live:
            self._live_host_replies.add(room_thread_id)
        return result

    async def fan_in_peer_turn(
        self,
        call: PeerCall,
        visible: list[Any],
        *,
        live_streamed: bool = False,
    ) -> None:
        """Persist the member's final bubble on the caller's room thread."""
        if not self._is_group_dispatch(call):
            return
        speaker = call.to_agent_id
        stamped = [_with_speaker(msg, speaker) for msg in _room_peer_messages(visible)]
        final = _final_room_assistant(stamped)
        if final is None:
            return
        if self._thread_message_repo is not None:
            try:
                self._thread_message_repo.append_if_ready(
                    call.source_thread_id,
                    live_message_inputs([final], dedupe_missing_ids=True),
                )
            except Exception:
                logger.warning(
                    "failed to fan-in team peer history thread=%s speaker=%s",
                    call.source_thread_id,
                    speaker,
                    exc_info=True,
                )
        room = str(call.source_thread_id or "").strip()
        text = _assistant_text(final)
        if not room:
            return
        await self._push_room_to_channels(room, speaker, text)
        if not live_streamed:
            await self._push_room_snapshot(room, speaker, text)

    def stamp_host_runtime(self, request: dict[str, Any], agent_id: str) -> None:
        """Force the host turn onto async ``ask_agent`` (inbox), not sync."""
        row = self._agent_manager.get_row(agent_id)
        if not is_team_agent(row):
            return
        cfg = dict(request.get("configurable") or {})
        cfg["peer_invoke_mode"] = "async"
        cfg.pop("mcp_use_default", None)
        request["configurable"] = cfg
        request.pop("mcp_servers", None)
        request.pop("mcp_use_default", None)
        strip = getattr(self._agent_manager, "strip_team_host_runtime_tools", None)
        if callable(strip):
            strip(agent_id)

    def stash_peer_prompt(
        self,
        agent_id: str,
        thread_id: str | None,
        *,
        question: str,
        dispatch: str,
    ) -> None:
        if not thread_id:
            return
        question = question.strip()
        dispatch = dispatch.strip()
        if not question and not dispatch:
            return
        self._peer_prompts[(agent_id, thread_id)] = (question, dispatch)

    def take_peer_prompt(self, agent_id: str, thread_id: str | None) -> tuple[str, str] | None:
        if not thread_id:
            return None
        return self._peer_prompts.pop((agent_id, thread_id), None)

    take_team_peer_prompt = take_peer_prompt
    stream_team_peer_to_room = stream_peer_to_room

    def peek_peer_prompt(self, agent_id: str, thread_id: str | None) -> tuple[str, str] | None:
        if not thread_id:
            return None
        return self._peer_prompts.get((agent_id, thread_id))

    def install_host_dispatch(self, harness_team: Any) -> None:
        """Force team hosts onto inbox dispatch and room streaming."""
        wire_host_dispatch(
            harness_team,
            is_team=lambda agent_id: is_team_agent(self._agent_manager.get_row(agent_id)),
            stream_peer=self.stream_peer_to_room,
            stream_host=self.stream_host_followup_to_room,
            take_prompt=self.take_peer_prompt,
        )

    # -- jobs / runtime -------------------------------------------------------

    def _jobs(self) -> Any:
        return getattr(self._agent_manager, "_team_jobs", None)

    def _track_job(self, call: PeerCall, *, begin: bool) -> None:
        host = self._agent_manager.get_row(call.from_agent_id)
        if not is_team_agent(host):
            return
        jobs = self._jobs()
        if jobs is None:
            return
        job_id = getattr(call, "job_id", None)
        if begin:
            jobs.begin(call.from_agent_id, call.to_agent_id, job_id=job_id)
        else:
            jobs.end(call.from_agent_id, call.to_agent_id, job_id=job_id)

    def _end_job_from_reply(self, event: ReplyEvent) -> None:
        jobs = self._jobs()
        if jobs is None:
            return
        source = str(event.source_agent_id or "")
        target = str(event.target_agent_id or "")
        if source and target:
            jobs.end(source, target, job_id=event.inbox_id)

    def _is_group_dispatch(self, call: PeerCall) -> bool:
        """Async ``ask_agent`` is a group room; sync is a 1:1 tool return.

        Inbox jobs always have ``job_id``. A team host without a job id is
        still treated as a room (hosts cannot sync-dispatch).
        """
        if not str(getattr(call, "source_thread_id", None) or "").strip():
            return False
        if getattr(call, "job_id", None):
            return True
        return is_team_agent(self._agent_manager.get_row(call.from_agent_id))

    def _member_runtime(self, call: PeerCall) -> dict[str, Any] | None:
        if not self._is_group_dispatch(call):
            return None
        extra: dict[str, Any] = {"peer_invoke_mode": "sync"}
        host = self._agent_manager.get_row(call.from_agent_id)
        if is_team_agent(host):
            extra["team_peers"] = [
                member_id
                for member_id in self._agent_manager.teams.member_ids(call.from_agent_id)
                if member_id != call.to_agent_id
            ]
        return extra

    def _ensure_projection(self, thread_id: str) -> None:
        """Mark a brand-new empty peer thread ready so we can append.

        Do not flip an existing pending thread to ready — that skips checkpoint
        backfill for legacy / 1:1 history.
        """
        repo = self._thread_message_repo
        if repo is None:
            return
        try:
            status = repo.projection_status(thread_id)
        except Exception:
            return
        if status != "pending":
            return
        try:
            page = repo.page(thread_id, limit=1, offset=0)
            rows = page[0] if isinstance(page, tuple) else page
        except Exception:
            return
        if rows:
            return
        repo.mark_projection(thread_id, "ready")

    def _seed_member_user_question(
        self,
        thread_id: str | None,
        prompt: str,
        *,
        turn_id: str | None = None,
    ) -> None:
        text = (prompt or "").strip()
        if not thread_id or not text or self._thread_message_repo is None:
            return
        self._ensure_projection(thread_id)
        try:
            self._thread_message_repo.append_if_ready(
                thread_id,
                message_inputs(
                    [HumanMessage(content=text, id=_peer_user_message_id(thread_id, turn_id))],
                    dedupe_missing_ids=True,
                ),
            )
        except Exception:
            logger.warning(
                "failed to seed peer user question thread=%s",
                thread_id,
                exc_info=True,
            )

    async def _assignment_text(self, call: PeerCall) -> str:
        """Host-rewritten task; fall back to the last room user line if empty."""
        text = str(call.message or "").strip()
        if text:
            return text
        if self._is_group_dispatch(call):
            return await self._visible_user_prompt(call)
        return ""

    def _locale_for(self, user_id: int | None) -> str:
        if user_id is None:
            return DEFAULT_LOCALE
        return resolve_user_locale(user_repo=self._user_repo, user_id=user_id)

    async def _dispatch_message(self, call: PeerCall, user_id: int | None) -> str:
        locale = self._locale_for(user_id)
        transcript = await self._room_transcript(
            call.source_thread_id,
            call.from_agent_id,
            locale,
        )
        if transcript:
            return tr(
                "teams.member_briefing_with_history",
                locale,
                history=transcript,
            )
        return tr("teams.member_briefing", locale)

    async def _visible_user_prompt(self, call: PeerCall) -> str:
        last = await self._last_room_user_text(call.source_thread_id, call.from_agent_id)
        if last:
            return last
        last = self._last_projected_user_text(call.source_thread_id)
        return last or str(call.message or "").strip()

    def _last_projected_user_text(self, thread_id: str | None) -> str:
        repo = self._thread_message_repo
        if not thread_id or repo is None:
            return ""
        try:
            if repo.projection_status(thread_id) != "ready":
                return ""
            rows, _ = repo.page(thread_id, limit=_ROOM_HISTORY_LIMIT, offset=0)
        except Exception:
            return ""
        for row in reversed(rows or []):
            if str(getattr(row, "role", "")).lower() not in {"human", "user"}:
                continue
            text = _projected_row_text(row)
            if text and not _is_team_system_prompt(text):
                return text
        return ""

    async def _last_room_user_text(self, thread_id: str | None, host_id: str) -> str:
        messages = await self._history(host_id, thread_id)
        for msg in reversed(messages or []):
            if _message_role(msg) not in {"human", "user"}:
                continue
            if _message_tool_calls(msg):
                continue
            text = _assistant_text(msg)
            if text and not _is_team_system_prompt(text):
                return text
        return ""

    async def _room_transcript(
        self,
        thread_id: str | None,
        host_id: str,
        locale: str,
    ) -> str:
        projected = self._projected_transcript(thread_id, host_id, locale)
        if projected:
            return projected
        messages = await self._history(host_id, thread_id)
        lines: list[str] = []
        for msg in messages or []:
            line = self._transcript_line(msg, host_id, locale)
            if line:
                lines.append(line)
        return "\n".join(lines)

    def _projected_transcript(
        self,
        thread_id: str | None,
        host_id: str,
        locale: str,
    ) -> str:
        repo = self._thread_message_repo
        if not thread_id or repo is None:
            return ""
        try:
            if repo.projection_status(thread_id) != "ready":
                return ""
            rows, _ = repo.page(thread_id, limit=_ROOM_HISTORY_LIMIT, offset=0)
        except Exception:
            return ""
        lines: list[str] = []
        for row in rows or []:
            line = self._projected_transcript_line(row, host_id, locale)
            if line:
                lines.append(line)
        return "\n".join(lines)

    def _projected_transcript_line(self, row: Any, host_id: str, locale: str) -> str | None:
        role = str(getattr(row, "role", "")).lower()
        text = _projected_row_text(row)
        if not text or _is_team_system_prompt(text):
            return None
        if role in {"human", "user"}:
            return self._channel_line(locale, tr("teams.speaker_user", locale), text)
        if role not in {"ai", "assistant"}:
            return None
        speaker = _projected_speaker(row) or host_id
        return self._channel_line(locale, self._display_name(speaker), text)

    async def _history(self, agent_id: str, thread_id: str | None) -> list[Any]:
        if not thread_id:
            return []
        getter = getattr(self._agent_manager, "get_agent", None)
        if getter is None:
            return []
        try:
            harness = getter(agent_id)
            hist = getattr(harness, "aget_history", None)
            if hist is None:
                return []
            return list(await hist(thread_id, limit=_ROOM_HISTORY_LIMIT) or [])
        except Exception:
            logger.warning(
                "failed to read team history thread=%s agent=%s",
                thread_id,
                agent_id,
                exc_info=True,
            )
            return []

    def _transcript_line(self, msg: Any, host_id: str, locale: str) -> str | None:
        role = _message_role(msg)
        if role in {"tool", "system"}:
            return None
        if _message_tool_calls(msg):
            return None
        text = _assistant_text(msg)
        if not text:
            return None
        if role in {"human", "user"}:
            return self._channel_line(locale, tr("teams.speaker_user", locale), text)
        if role not in {"ai", "assistant"}:
            return None
        kwargs = (
            msg.get("additional_kwargs")
            if isinstance(msg, dict)
            else getattr(msg, "additional_kwargs", None)
        ) or {}
        speaker = str(kwargs.get("speaker_agent_id") or host_id)
        return self._channel_line(locale, self._display_name(speaker), text)

    def _channel_line(self, locale: str, name: str, text: str) -> str:
        return tr("teams.channel_line", locale, name=name, text=text)

    def _title_member_thread(self, call: PeerCall, thread_id: str, user_id: int) -> None:
        host = self._agent_manager.get_row(call.from_agent_id)
        if not is_team_agent(host):
            return
        locale = self._locale_for(user_id)
        title = tr(
            "teams.peer_thread_title", locale, name=host.name if host else call.from_agent_id
        )
        self._thread_registry.set_title_if_null(thread_id, title)

    async def _relay_chunk(
        self,
        chunk: dict[str, Any],
        *,
        room_thread_id: str,
        member_thread_id: str,
        speaker_id: str,
    ) -> None:
        hub = getattr(self._gateway, "ws_hub", None) if self._gateway is not None else None
        if hub is None:
            return
        stamped = stamp_stream_speaker(chunk, speaker_id, include_done=True)
        try:
            if room_thread_id:
                await hub.push_to_thread(room_thread_id, stamped)
            if member_thread_id and member_thread_id != room_thread_id:
                await hub.push_to_thread(member_thread_id, chunk)
        except Exception:
            logger.warning(
                "failed to relay team peer chunk speaker=%s room=%s",
                speaker_id,
                room_thread_id,
                exc_info=True,
            )

    async def _peer_result_messages(
        self,
        speaker_id: str,
        member_tid: str,
        text_parts: list[str],
        reasoning_parts: list[str] | None = None,
    ) -> list[Any]:
        reasoning = "".join(reasoning_parts or []).strip()
        messages = await self._history(speaker_id, member_tid)
        if messages:
            room = _room_peer_messages(messages)
            if room:
                stamped = [_with_speaker(msg, speaker_id) for msg in room]
                if reasoning:
                    for msg in reversed(stamped):
                        if _message_is_assistant(msg):
                            _ensure_reasoning(msg, reasoning)
                            break
                return stamped
        text = "".join(text_parts).strip()
        if not text and not reasoning:
            return []
        extra: dict[str, Any] = {"speaker_agent_id": speaker_id}
        if reasoning:
            extra["reasoning_content"] = reasoning
        return [
            AIMessage(
                content=text,
                id=f"team-peer:{new_ulid()}:assistant",
                additional_kwargs=extra,
            )
        ]

    def _take_live_host_reply(self, thread_id: str | None) -> bool:
        tid = str(thread_id or "").strip()
        if not tid or tid not in self._live_host_replies:
            return False
        self._live_host_replies.discard(tid)
        return True

    def _persist_room_assistant(
        self,
        thread_id: str,
        speaker_id: str,
        text: str,
        *,
        wrapup: bool = False,
    ) -> None:
        body = (text or "").strip()
        if not thread_id or not body or self._thread_message_repo is None:
            return
        self._ensure_projection(thread_id)
        extra: dict[str, Any] = {"speaker_agent_id": speaker_id}
        if wrapup:
            extra["team_wrapup"] = True
        msg = AIMessage(
            content=body,
            id=f"team-room:{new_ulid()}:assistant",
            additional_kwargs=extra,
        )
        try:
            self._thread_message_repo.append_if_ready(
                thread_id,
                message_inputs([msg], dedupe_missing_ids=True),
            )
        except Exception:
            logger.warning(
                "failed to persist team room text thread=%s speaker=%s",
                thread_id,
                speaker_id,
                exc_info=True,
            )

    async def _push_session_channel(self, session: SessionRow, text: str) -> None:
        if self._gateway is None:
            return
        await self._gateway.push_text(
            session.channel_type,
            session.channel_id,
            session.to_channel_subject(),
            text,
        )

    async def _push_room_to_channels(
        self,
        thread_id: str,
        speaker_id: str,
        text: str,
        *,
        prefix_speaker: bool = True,
    ) -> None:
        """Push a finished room bubble to IM sessions bound to this thread.

        Dashboard / CLI already receive the room WebSocket stream. Channels only
        see the host's inbound turn unless we deliver member (and wrap-up) text
        here as a complete outbound message.
        """
        body = (text or "").strip()
        if not thread_id or not body or self._gateway is None:
            return
        for session in self._thread_registry.im_sessions_for_thread(thread_id):
            outbound = (
                self._channel_line(
                    self._locale_for(int(session.user_id)),
                    self._display_name(speaker_id),
                    body,
                )
                if prefix_speaker
                else body
            )
            try:
                await self._push_session_channel(session, outbound)
            except Exception:
                logger.warning(
                    "failed to push team speech to channel thread=%s speaker=%s",
                    thread_id,
                    speaker_id,
                    exc_info=True,
                )

    async def _publish_room_text(self, thread_id: str, speaker_id: str, text: str) -> None:
        body = (text or "").strip()
        if not thread_id or not body:
            return
        self._persist_room_assistant(thread_id, speaker_id, body, wrapup=True)
        await self._push_room_snapshot(
            thread_id,
            speaker_id,
            body,
            wrapup=True,
        )

    async def _push_room_snapshot(
        self,
        thread_id: str,
        speaker_id: str,
        text: str,
        *,
        wrapup: bool = False,
    ) -> None:
        body = (text or "").strip()
        if not thread_id or not body:
            return
        hub = getattr(self._gateway, "ws_hub", None) if self._gateway is not None else None
        if hub is None:
            return
        extra = {"team_wrapup": True} if wrapup else {"team_snapshot": True}
        try:
            await hub.push_to_thread(
                thread_id,
                stamp_stream_speaker(
                    {"type": "token", "content": body, **extra},
                    speaker_id,
                ),
            )
            await hub.push_to_thread(
                thread_id,
                stamp_stream_speaker(
                    {"type": "done", **extra},
                    speaker_id,
                    include_done=True,
                ),
            )
        except Exception:
            logger.warning(
                "failed to push team room stream thread=%s speaker=%s",
                thread_id,
                speaker_id,
                exc_info=True,
            )

    def _thread_is_watched(self, thread_id: str) -> bool:
        hub = getattr(self._gateway, "ws_hub", None) if self._gateway is not None else None
        checker = getattr(hub, "has_subscribers", None)
        return bool(callable(checker) and checker(thread_id))

    async def _deliver_text(
        self,
        session: SessionRow,
        session_key: str,
        text: str,
        *,
        speaker_id: str | None = None,
    ) -> None:
        if self._thread_registry.is_im_session(session):
            await self._push_session_channel(session, text)
            return
        await self._publish_room_text(
            session.thread_id,
            speaker_id or session.agent_id,
            text,
        )
        if not self._thread_is_watched(session.thread_id):
            self._thread_registry.increment_unread(session_key)
        self._thread_registry.touch_last_active(session.thread_id)

    def _display_name(self, agent_id: str) -> str:
        row = self._agent_manager.get_row(agent_id)
        return row.name if row is not None else agent_id[-6:]

    def _touch_thread(self, thread_id: str, title_source: str | None) -> None:
        self._thread_registry.touch_last_active(thread_id)
        if title_source:
            self._thread_registry.set_title_if_null(thread_id, title_source)


def _chunk_speaker_id(chunk: dict[str, Any]) -> str:
    """Read a live-frame speaker. Ignore LangGraph's ``agent`` node name."""
    for key in ("agent_id", "agent", "speaker_agent_id"):
        raw = chunk.get(key)
        if not isinstance(raw, str):
            continue
        value = raw.strip()
        if not value:
            continue
        if key == "agent" and value == "agent":
            continue
        return value
    return ""


def stamp_stream_speaker(
    chunk: dict[str, Any],
    speaker_id: str,
    *,
    include_done: bool = False,
) -> dict[str, Any]:
    """Copy a stream frame and set ``agent`` / ``agent_id`` to the speaker."""
    if not isinstance(chunk, dict) or not speaker_id:
        return chunk
    kind = str(chunk.get("type") or "")
    if kind == "done" and not include_done:
        return chunk
    if kind not in _STREAM_SPEAKER_TYPES:
        return chunk
    if chunk.get("agent_id") == speaker_id and chunk.get("agent") == speaker_id:
        return chunk
    out = dict(chunk)
    out["agent_id"] = speaker_id
    out["agent"] = speaker_id
    return out


def stamp_team_host_chunk(
    chunk: dict[str, Any],
    agent_id: str,
    team_host: bool,
) -> dict[str, Any]:
    if not team_host:
        return chunk
    existing = _chunk_speaker_id(chunk)
    if existing and existing != agent_id:
        return chunk
    return stamp_stream_speaker(chunk, agent_id, include_done=True)


def _peer_user_message_id(thread_id: str, turn_id: str | None = None) -> str:
    suffix = (turn_id or "").strip() or new_ulid()
    return f"team-peer:{thread_id}:{suffix}:human"


def _is_team_system_prompt(text: str) -> bool:
    head = text.lstrip()
    return head.startswith(
        (
            "[团队成员",
            "[系统唤醒",
            "[团队派工",
            "[主持人调度",
            "[team member",
            "[system wake-up",
            "[background task",
            "[Team assignment",
            "[Host dispatch",
            "以下是当前群聊记录",
            "Here is the current group-chat transcript",
        )
    )


def _projected_row_text(row: Any) -> str:
    raw = getattr(row, "message_json", "") or ""
    try:
        wire = json.loads(raw)
    except json.JSONDecodeError:
        return str(raw).strip()
    data = wire.get("data") if isinstance(wire, dict) else None
    content = data.get("content") if isinstance(data, dict) else None
    if content is None and isinstance(wire, dict):
        content = wire.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text") or ""))
        return "".join(parts).strip()
    return str(content or "").strip()


def _projected_kwargs(row: Any) -> dict[str, Any]:
    raw = getattr(row, "message_json", "") or ""
    try:
        wire = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(wire, dict):
        return {}
    data = wire.get("data")
    kwargs = data.get("additional_kwargs") if isinstance(data, dict) else None
    if not isinstance(kwargs, dict):
        kwargs = wire.get("additional_kwargs")
    return kwargs if isinstance(kwargs, dict) else {}


def _projected_speaker(row: Any) -> str:
    speaker = _projected_kwargs(row).get("speaker_agent_id")
    return str(speaker).strip() if speaker else ""


def _make_peer_session(**kwargs: Any) -> PeerSession:
    allowed = {item.name for item in fields(PeerSession)}
    return PeerSession(**{key: value for key, value in kwargs.items() if key in allowed})


def _chat_request_payload(request: Any, speaker_id: str) -> dict[str, Any]:
    if isinstance(request, dict):
        payload = dict(request)
    else:
        payload = {
            "messages": getattr(request, "messages", ""),
            "thread_id": getattr(request, "thread_id", None),
            "user": getattr(request, "user", None),
            "source": getattr(request, "source", None),
            "agent_id": getattr(request, "agent_id", None),
            "model": getattr(request, "model", None),
            "configurable": getattr(request, "configurable", None),
            "mcp_servers": getattr(request, "mcp_servers", None),
            "mcp_use_default": bool(getattr(request, "mcp_use_default", False)),
        }
        payload = {
            key: value for key, value in payload.items() if value is not None and value is not False
        }
        if getattr(request, "mcp_use_default", False):
            payload["mcp_use_default"] = True
        if "messages" not in payload:
            payload["messages"] = ""
    if not payload.get("agent_id"):
        payload["agent_id"] = speaker_id
    return payload


def _octop_user_id(user_id: str | int) -> int | None:
    if isinstance(user_id, int):
        return user_id if user_id > 0 else None
    if isinstance(user_id, str) and user_id.isdigit():
        uid = int(user_id)
        return uid if uid > 0 else None
    return None


def _message_role(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("role") or msg.get("type") or "").lower()
    return str(getattr(msg, "type", None) or getattr(msg, "role", "") or "").lower()


def _message_is_assistant(msg: Any) -> bool:
    return _message_role(msg) in {"ai", "assistant"}


def _message_tool_calls(msg: Any) -> Any:
    if isinstance(msg, dict):
        return msg.get("tool_calls")
    return getattr(msg, "tool_calls", None)


def _final_room_assistant(messages: list[Any]) -> Any | None:
    for msg in reversed(messages):
        if not _message_is_assistant(msg) or _message_tool_calls(msg):
            continue
        if _assistant_text(msg):
            return msg
    return None


def _with_speaker(msg: Any, agent_id: str) -> Any:
    if isinstance(msg, dict):
        kwargs = dict(msg.get("additional_kwargs") or {})
        if kwargs.get("speaker_agent_id") == agent_id:
            return msg
        kwargs["speaker_agent_id"] = agent_id
        out = dict(msg)
        out["additional_kwargs"] = kwargs
        return out
    kwargs = dict(getattr(msg, "additional_kwargs", None) or {})
    if kwargs.get("speaker_agent_id") == agent_id:
        return msg
    kwargs["speaker_agent_id"] = agent_id
    copy = getattr(msg, "model_copy", None)
    if callable(copy):
        try:
            return copy(update={"additional_kwargs": kwargs})
        except Exception:
            pass
    try:
        object.__setattr__(msg, "additional_kwargs", kwargs)
    except Exception:
        msg.additional_kwargs = kwargs
    return msg


def _ensure_reasoning(msg: Any, reasoning: str) -> None:
    if not reasoning:
        return
    if isinstance(msg, dict):
        kwargs = dict(msg.get("additional_kwargs") or {})
        if not str(kwargs.get("reasoning_content") or "").strip():
            kwargs["reasoning_content"] = reasoning
            msg["additional_kwargs"] = kwargs
        return
    kwargs = dict(getattr(msg, "additional_kwargs", None) or {})
    if str(kwargs.get("reasoning_content") or "").strip():
        return
    kwargs["reasoning_content"] = reasoning
    try:
        object.__setattr__(msg, "additional_kwargs", kwargs)
    except Exception:
        msg.additional_kwargs = kwargs


def _room_peer_messages(messages: list[Any]) -> list[Any]:
    last_user = -1
    for index, msg in enumerate(messages):
        if _message_role(msg) in {"human", "user"}:
            last_user = index
    tail = messages[last_user + 1 :] if last_user >= 0 else list(messages)
    skip = {"system", "human", "user"}
    return [msg for msg in tail if _message_role(msg) not in skip]


def _assistant_text(msg: Any) -> str:
    content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "\n".join(p for p in parts if p).strip()
    return str(content or "").strip()


def _peer_turn_messages(messages: list[Any]) -> list[Any]:
    trigger: Any | None = None
    final_ai: Any | None = None
    for msg in messages:
        role = ""
        if isinstance(msg, dict):
            role = str(msg.get("role") or msg.get("type") or "").lower()
            tool_calls = msg.get("tool_calls")
        else:
            role = str(getattr(msg, "type", None) or getattr(msg, "role", "") or "").lower()
            tool_calls = getattr(msg, "tool_calls", None)
        if role in ("human", "user"):
            trigger = msg
        if role in ("ai", "assistant") and not tool_calls:
            final_ai = msg
    out: list[Any] = []
    if trigger is not None:
        out.append(trigger)
    if final_ai is not None:
        out.append(final_ai)
    return out


def _is_async_room_invoke(
    *,
    source: str | None,
    job_id: str | None,
    source_thread_id: str | None,
) -> bool:
    """Live-stream a peer when this is an inbox/async room dispatch."""
    if not str(source_thread_id or "").strip():
        return False
    return str(source or "") == "inbox" or bool(job_id)


def _supported_kwargs(fn: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return dict(kwargs)
    if any(item.kind is inspect.Parameter.VAR_KEYWORD for item in params.values()):
        return dict(kwargs)
    return {key: value for key, value in kwargs.items() if key in params}


def _patch_inbox_wrapup(
    inbox: Any,
    *,
    stream_followup: Callable[..., Any] | None,
    is_team: Callable[[str], bool] | None = None,
) -> None:
    """Run async host wrap-up through the room stream, not a blocking ``call()``."""
    if inbox is None or stream_followup is None:
        return
    original = getattr(inbox, "_synthesize_reply", None)
    if original is None:
        return

    async def _fallback(msg: Any, result_text: str | None, error_text: str | None) -> str | None:
        reply = await original(msg, result_text, error_text)
        if reply is None or isinstance(reply, str):
            return reply
        return str(reply)

    async def synthesize(
        msg: Any,
        result_text: str | None,
        error_text: str | None,
    ) -> str | None:
        cancelled = getattr(inbox, "_is_cancelled", None)
        if callable(cancelled) and cancelled(msg):
            return None
        room = str(getattr(msg, "source_thread_id", None) or "").strip()
        host_id = str(getattr(msg, "source_agent_id", None) or "")
        if not host_id or not room:
            return await _fallback(msg, result_text, error_text)
        if callable(is_team) and not is_team(host_id):
            return await _fallback(msg, result_text, error_text)
        processor = getattr(inbox, "_processor", None)
        compose = getattr(processor, "compose_followup", None)
        if compose is None:
            return await _fallback(msg, result_text, error_text)
        prompt = compose(msg, result_text=result_text, error_text=error_text)
        req = build_one_shot_request(
            user_id=msg.user_id,
            agent_id=host_id,
            text=prompt,
            source="inbox",
        )
        try:
            reply = await stream_followup(
                req,
                room_thread_id=room,
                speaker_id=host_id,
            )
        except Exception:
            logger.exception("team host wrap-up stream failed host=%s room=%s", host_id, room)
            return await _fallback(msg, result_text, error_text)
        if isinstance(reply, dict):
            return extract_call_response(reply)
        return ""

    inbox._synthesize_reply = synthesize


def wire_host_dispatch(
    harness_team: Any,
    *,
    is_team: Callable[[str], bool],
    stream_peer: Callable[..., Any] | None = None,
    stream_host: Callable[..., Any] | None = None,
    take_prompt: Callable[[str, str | None], tuple[str, str] | None] | None = None,
) -> None:
    """Patch harness TeamManager so async ``ask_agent`` uses inbox + room stream."""
    if harness_team is None:
        return
    original_call = getattr(harness_team, "call_peer", None)

    async def call_peer(
        *,
        from_agent_id: str,
        to_agent_id: str,
        message: str,
        user_id: str | int,
        source: str = "ask_agent",
        source_thread_id: str | None = None,
        session_key: str | None = None,
        **kwargs: Any,
    ) -> Any:
        if getattr(harness_team, "enabled", False) and is_team(from_agent_id):
            return harness_team.submit_peer(
                from_agent_id=from_agent_id,
                to_agent_id=to_agent_id,
                message=message,
                user_id=user_id,
                source_thread_id=source_thread_id,
                metadata={"session_key": session_key} if session_key else None,
            )
        if original_call is None:
            raise TypeError("harness team has no call_peer")
        return await original_call(
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
            message=message,
            user_id=user_id,
            source=source,
            source_thread_id=source_thread_id,
            session_key=session_key,
            **kwargs,
        )

    harness_team.call_peer = call_peer

    stream_followup = stream_host or stream_peer
    original_call_agent = getattr(harness_team, "_call_agent", None)
    if original_call_agent is not None and stream_followup is not None:

        async def call_agent(agent_id: str, request: Any) -> Any:
            source = getattr(request, "source", None)
            if isinstance(request, dict):
                source = request.get("source")
            thread_id = getattr(request, "thread_id", None)
            if isinstance(request, dict):
                thread_id = request.get("thread_id")
            room = str(thread_id or "").strip()
            if source == "inbox" and room and is_team(agent_id):
                return await stream_followup(
                    request,
                    room_thread_id=room,
                    speaker_id=agent_id,
                )
            return await original_call_agent(agent_id, request)

        harness_team._call_agent = call_agent
        inbox = getattr(harness_team, "inbox", None)
        if inbox is not None:
            inbox._call_agent = call_agent

    _patch_inbox_wrapup(
        getattr(harness_team, "inbox", None),
        stream_followup=stream_followup,
        is_team=is_team,
    )

    original_invoke = getattr(harness_team, "_invoke_peer", None)
    if original_invoke is not None and stream_peer is not None:

        async def invoke_peer(
            *,
            from_agent_id: str,
            to_agent_id: str,
            message: str,
            user_id: str | int,
            source: str,
            source_thread_id: str | None,
            source_session_key: str | None,
            job_id: str | None = None,
        ) -> Any:
            peer_kwargs = {
                "from_agent_id": from_agent_id,
                "to_agent_id": to_agent_id,
                "message": message,
                "user_id": user_id,
                "source": source,
                "source_thread_id": source_thread_id,
                "source_session_key": source_session_key,
                "job_id": job_id,
            }
            if not _is_async_room_invoke(
                source=source,
                job_id=job_id,
                source_thread_id=source_thread_id,
            ):
                return await original_invoke(**_supported_kwargs(original_invoke, peer_kwargs))
            request = await harness_team._build_peer_request(
                **_supported_kwargs(harness_team._build_peer_request, peer_kwargs)
            )
            enrich = getattr(harness_team, "_enrich_request", None)
            if enrich is not None:
                request = await enrich(to_agent_id, request)
            result = await stream_peer(
                request,
                room_thread_id=source_thread_id,
                speaker_id=to_agent_id,
            )
            payload = result if isinstance(result, dict) else {}
            after = getattr(harness_team, "_after_peer", None)
            if after is not None:
                call = PeerCall(**_supported_kwargs(PeerCall, peer_kwargs))
                try:
                    await after(call, str(getattr(request, "thread_id", None) or ""), payload)
                except Exception:
                    logger.warning(
                        "peer after-call hook failed for %s -> %s",
                        from_agent_id,
                        to_agent_id,
                        exc_info=True,
                    )
            return request, payload

        harness_team._invoke_peer = invoke_peer

    if take_prompt is None:
        return
    original_enrich = getattr(harness_team, "_enrich_request", None)

    async def enrich(agent_id: str, req: Any) -> Any:
        if original_enrich is not None:
            req = await original_enrich(agent_id, req)
        pair = take_prompt(agent_id, getattr(req, "thread_id", None))
        if not pair:
            return req
        from langchain_core.messages import HumanMessage, SystemMessage

        question, dispatch = pair
        messages: list[Any] = []
        if dispatch and dispatch != question:
            messages.append(SystemMessage(content=dispatch))
        if question:
            messages.append(
                HumanMessage(
                    content=question,
                    id=f"team-peer:{getattr(req, 'thread_id', None)}:{new_ulid()}:human",
                )
            )
        if messages:
            req.messages = messages
        return req

    harness_team._enrich_request = enrich


__all__ = [
    "TeamManager",
    "host_system_prompt",
    "stamp_stream_speaker",
    "stamp_team_host_chunk",
    "wire_host_dispatch",
]
