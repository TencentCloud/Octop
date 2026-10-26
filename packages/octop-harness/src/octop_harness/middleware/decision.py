"""Narrow skills, tools, and team members with a decision model before the chat model speaks.

Mounted only when :func:`octop_harness.decision.decision_active` is true.
A low score, a failed request, or a user who already named a teammate leaves
that catalog as it was.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from typing import Any, cast

from deepagents.middleware._utils import append_to_system_message
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.types import AgentState
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from octop_harness.context_usage import catalog_saved_tokens, pending_decision_saved
from octop_harness.decision.client import HttpDecisionClient
from octop_harness.decision.config import DecisionConfig
from octop_harness.decision.select import Candidate, keep_confident, lexical_shortlist
from octop_harness.middleware.peer import has_agent_at_mention
from octop_harness.middleware.runtime import runtime_config
from octop_harness.teams.profile import peer_description
from octop_harness.teams.util import coerce_user_id

logger = logging.getLogger(__name__)

# Set while one model call is being scored, then copied onto that reply so
# history can show the same row the live stream already showed.
_PENDING_DECISION: ContextVar[dict[str, Any] | None] = ContextVar(
    "octop_pending_decision",
    default=None,
)

# Decision APIs take a short situation string, not the chat model window.
# Newest turns win when this budget is exceeded.
_STATE_LIMIT = 2400
_BLURB_LIMIT = 240
_QUESTION_LIMIT = 20
_CATALOG_LIMIT = 12
# Near misses stay. 0.6 still prefers a clear yes; 0.45 is kept while there is room.
_KEEP_SLACK = 0.15
# Filesystem, todos, memory, team dispatch, web lookup, and irreplaceable
# delivery/browse/screenshot tools. Decision may still drop the long tail
# (MCP/plugins, env file, media generation, etc.).
# Dropping the core set makes the chat model print a raw tool call and stop.
# ask_agent / agent_list are how a team host schedules; they stay even when
# every other tool is filtered out.
_TOOLS_ALWAYS_KEPT = frozenset(
    {
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "delete",
        "glob",
        "grep",
        "execute",
        "write_todos",
        "task",
        "current_time",
        "tool_search",
        "memory_search",
        "memory_get",
        "agent_list",
        "ask_agent",
        "web_fetch",
        "tavily_search",
        "brave_search",
        "google_search",
        "kimi_search",
        "deepseek_search",
        "yuanbao_search",
        "searchfree_search",
        "you_search",
        "send_file_to_user",
        "browser_use",
        "desktop_screenshot",
    }
)
# Shown on the host decision card. They are not scored: a low score must not
# take away the host's ability to dispatch.
_HOST_DISPATCH_TOOLS = ("ask_agent", "agent_list")
# Matches no teammate. A wrap-up that clears nobody closes dispatch for the
# rest of that turn.
_DISPATCH_CLOSED = frozenset({"\x00"})
_AGENT_AT_TOKEN_RE = re.compile(r"@([^\W\d_][\w\-]*)(?![\w./\-~]*\.\w)")


def _call_with_savings(
    before: ModelRequest,
    after: ModelRequest,
    handler: Callable[[ModelRequest], ModelResponse],
) -> ModelResponse:
    token = pending_decision_saved.set(catalog_saved_tokens(before, after))
    try:
        return handler(after)
    finally:
        pending_decision_saved.reset(token)


async def _call_with_savings_async(
    before: ModelRequest,
    after: ModelRequest,
    handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
) -> ModelResponse:
    token = pending_decision_saved.set(catalog_saved_tokens(before, after))
    try:
        return await handler(after)
    finally:
        pending_decision_saved.reset(token)


def _stamp_decision(response: ModelResponse, payload: dict[str, Any] | None) -> ModelResponse:
    """Copy this turn's decision onto the reply so history can render it."""
    if not payload:
        return response
    result = getattr(response, "result", None)
    if not isinstance(result, list):
        return response
    stamped: list[Any] = []
    attached = False
    for message in result:
        if not attached and isinstance(message, AIMessage):
            extra = dict(message.additional_kwargs or {})
            extra["octop_decision"] = payload
            stamped.append(message.model_copy(update={"additional_kwargs": extra}))
            attached = True
        else:
            stamped.append(message)
    if not attached:
        return response
    return replace(response, result=stamped)


def _stringify_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content or "")


def _latest_user_text(request: ModelRequest) -> str:
    messages = getattr(request, "messages", None) or []
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return _stringify_content(msg.content).strip()
    return ""


def _tool_name(tool: Any) -> str:
    if isinstance(tool, dict):
        fn = tool.get("function")
        if isinstance(fn, dict) and fn.get("name"):
            return str(fn["name"])
        if tool.get("name"):
            return str(tool["name"])
        return ""
    return str(getattr(tool, "name", "") or "")


def _tool_description(tool: Any) -> str:
    if isinstance(tool, dict):
        fn = tool.get("function")
        if isinstance(fn, dict):
            return str(fn.get("description") or "")
        return str(tool.get("description") or "")
    return str(getattr(tool, "description", "") or "")


def _clip(text: str, limit: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _statement(kind: str, label: str, description: str, *, chinese: bool) -> str:
    blurb = _clip(description, _BLURB_LIMIT)
    detail = f" {blurb}" if blurb else ""
    if chinese:
        if kind == "skill":
            return f"这轮需要技能「{label}」。{detail}".strip()
        if kind == "tool":
            return f"这轮需要工具「{label}」。{detail}".strip()
        return f"这轮应该派给成员「{label}」。{detail}".strip()
    if kind == "skill":
        return f'The skill "{label}" is needed for this request.{detail}'
    if kind == "tool":
        return f'The tool "{label}" is needed for this request.{detail}'
    return f'The teammate "{label}" should work on this request.{detail}'


@dataclass
class _TurnFilter:
    """Frozen catalog for one user message, including the tool loop after it.

    ``None`` means that side was not narrowed. Later model calls replay this
    instead of sending the full tool and skill definitions again.
    """

    tools: set[str] | None = None
    skills: set[str] | None = None


@dataclass
class _Work:
    statements: list[tuple[str, str]] = field(default_factory=list)
    skill_ids: list[str] | None = None
    skill_rows: list[dict[str, Any]] | None = None
    tool_ids: list[str] | None = None
    tools_in: list[Any] | None = None
    member_ids: list[str] | None = None
    forced_member_ids: list[str] = field(default_factory=list)
    member_labels: dict[str, str] = field(default_factory=dict)
    member_keys: dict[str, frozenset[str]] = field(default_factory=dict)
    thread_key: str = ""
    turn_key: str = ""
    asked_skills: list[str] = field(default_factory=list)
    asked_tools: list[str] = field(default_factory=list)
    asked_members: list[str] = field(default_factory=list)
    result_check: bool = False


class DecisionMiddleware(AgentMiddleware[Any, Any]):
    """Ask one decision model which skills, tools, and teammates to keep."""

    def __init__(
        self,
        *,
        config: DecisionConfig,
        team: Any | None = None,
        language: str = "zh",
        scorer: Any | None = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._team = team
        self._chinese = language != "en"
        self._scorer = scorer or HttpDecisionClient(
            endpoint=config.endpoint,
            api_key=config.api_key,
            model=config.model,
            provider=config.provider,
        )
        self._pins: dict[str, frozenset[str]] = {}
        self._turns: dict[str, _TurnFilter] = {}

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        token = _PENDING_DECISION.set(None)
        try:
            cached = self._turns.get(_turn_key(request))
            if cached is not None:
                narrowed = self._replay(request, cached)
            else:
                narrowed = self._finish(request, self._scorer.score)
            response = _call_with_savings(request, narrowed, handler)
            return _stamp_decision(response, _PENDING_DECISION.get())
        finally:
            _PENDING_DECISION.reset(token)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        token = _PENDING_DECISION.set(None)
        try:
            cached = self._turns.get(_turn_key(request))
            if cached is not None:
                narrowed = self._replay(request, cached)
            else:
                work = self._collect(request)
                if work is None:
                    narrowed = request
                else:
                    probabilities = await self._scorer.score_async(
                        state=_state_text(request, chinese=self._chinese),
                        statements=work.statements,
                    )
                    narrowed = self._apply(request, work, probabilities)
            response = await _call_with_savings_async(request, narrowed, handler)
            return _stamp_decision(response, _PENDING_DECISION.get())
        finally:
            _PENDING_DECISION.reset(token)

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        blocked = self._blocked_ask(request)
        if blocked is not None:
            return blocked
        result = handler(request)
        return self._filter_agent_list(request, result)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        blocked = self._blocked_ask(request)
        if blocked is not None:
            return blocked
        result = await handler(request)
        return self._filter_agent_list(request, result)

    def _finish(
        self,
        request: ModelRequest,
        score: Callable[..., dict[str, float]],
    ) -> ModelRequest:
        work = self._collect(request)
        if work is None:
            return request
        probabilities = score(
            state=_state_text(request, chinese=self._chinese),
            statements=work.statements,
        )
        return self._apply(request, work, probabilities)

    def _collect(self, request: ModelRequest) -> _Work | None:
        text = _latest_user_text(request)
        thread_key = _thread_key(request)
        self._pins.pop(thread_key, None)
        if not text:
            return None
        work = _Work(thread_key=thread_key, turn_key=_turn_key(request))
        cfg = self._config
        catalog_text = _followup_task(request) if _is_followup(request) else _user_history_text(request)
        if not catalog_text:
            catalog_text = _earlier_user_text(request) if _is_followup(request) else text
        if cfg.skills:
            self._collect_skills(request, catalog_text, work)
        if cfg.tools:
            self._collect_tools(request, catalog_text, work)
        if cfg.team:
            self._collect_members(request, text, work)
        if not work.statements:
            return None
        _fit_questions(work)
        if not work.statements:
            return None
        return work

    def _collect_skills(self, request: ModelRequest, text: str, work: _Work) -> None:
        raw = request.state.get("skills_metadata")
        rows = [row for row in raw if isinstance(row, dict)] if isinstance(raw, list) else []
        candidates = [
            Candidate(
                id=name,
                label=name,
                description=_clip(str(row.get("description") or ""), _BLURB_LIMIT),
            )
            for row in rows
            if (name := str(row.get("name") or "").strip())
        ]
        if len(candidates) < 2:
            return
        chosen = lexical_shortlist(candidates, text, limit=_CATALOG_LIMIT)
        if not chosen:
            return
        work.skill_rows = rows
        work.skill_ids = [item.id for item in chosen]
        for item in chosen:
            work.statements.append(
                ("skill:" + item.id, _statement("skill", item.label, item.description, chinese=self._chinese))
            )

    def _collect_tools(self, request: ModelRequest, text: str, work: _Work) -> None:
        tools_in = list(request.tools or [])
        named = [name for tool in tools_in if (name := _tool_name(tool))]
        if len(named) <= self._config.tool_min_count:
            return
        # Builtin tools stay in context. Spending a question on them only
        # crowds out the long tail the decision model can actually drop.
        candidates = [
            Candidate(id=name, label=name, description=_clip(_tool_description(tool), _BLURB_LIMIT))
            for tool in tools_in
            if (name := _tool_name(tool)) and name not in _TOOLS_ALWAYS_KEPT
        ]
        if not candidates:
            return
        chosen = lexical_shortlist(candidates, text, limit=_CATALOG_LIMIT)
        if not chosen:
            return
        work.tools_in = tools_in
        work.tool_ids = [item.id for item in chosen]
        for item in chosen:
            work.statements.append(
                ("tool:" + item.id, _statement("tool", item.label, item.description, chinese=self._chinese))
            )

    def _collect_members(self, request: ModelRequest, text: str, work: _Work) -> None:
        if self._team is None:
            return
        configurable = runtime_config(request).get("configurable") or {}
        if not self._async_dispatch(configurable):
            return
        user_id = coerce_user_id(configurable.get("user"))
        agent_id = str(configurable.get("agent_id") or "")
        if user_id is None or not agent_id:
            return
        # A member completion always gets a sufficiency check, even when the
        # roster has nobody left to dispatch. This is the host's final-result
        # evaluation and must not disappear merely because the team is small.
        followup = _is_followup(request)
        if followup:
            work.result_check = True
            statement = (
                "当前成员结果已经足以回答用户原始请求, 主持人现在可以总结, 不需要继续派工."
                if self._chinese
                else (
                    "The current member result is sufficient to answer the user's original request; "
                    "the host can summarize now without further dispatch."
                )
            )
            work.statements.append(("result:sufficient", statement))
        try:
            peers = self._team.list_peers(user_id, exclude_agent_id=agent_id)
        except Exception:
            logger.warning("decision member list failed", exc_info=True)
            return
        candidates: list[Candidate] = []
        labels: dict[str, str] = {}
        keys: dict[str, frozenset[str]] = {}
        for entry in peers:
            agent = str(getattr(entry, "agent_id", "") or "")
            if not agent:
                continue
            label = str(self._team.peer_display_name(entry) or agent)
            description = peer_description(getattr(entry, "metadata", None) or {}, "zh" if self._chinese else "en")
            candidates.append(Candidate(id=agent, label=label, description=_clip(description, _BLURB_LIMIT)))
            labels[agent] = label
            keys[agent] = frozenset(item.lower() for item in (agent, agent[-6:], label) if str(item).strip())
        # A wrap-up names whoever just finished. That is not the user picking
        # the next teammate, and that member is not a candidate to pin again.
        if followup:
            finished = _finished_member(request)
            if finished:
                candidates = [item for item in candidates if item.id != finished]
                labels.pop(finished, None)
                keys.pop(finished, None)
        naming = _earlier_user_text(request) if followup else text
        candidates, labels, keys, forced, stop = _restrict_named_members(
            naming,
            candidates,
            labels,
            keys,
            followup=followup,
        )
        if stop:
            return
        work.forced_member_ids = forced
        work.member_ids = [item.id for item in candidates]
        work.member_labels = labels
        work.member_keys = keys
        for item in candidates:
            work.statements.append(
                ("member:" + item.id, _statement("member", item.label, item.description, chinese=self._chinese))
            )

    def _apply(self, request: ModelRequest, work: _Work, probabilities: dict[str, float]) -> ModelRequest:
        if not probabilities:
            self._remember_turn(work.turn_key, _TurnFilter())
            self._publish(empty=True, parts=[])
            return request
        parts: list[dict[str, Any]] = []
        skill_kept: set[str] | None = None
        tool_kept: set[str] | None = None
        result_sufficient = False
        if work.skill_ids and work.skill_rows is not None:
            request, part, skill_kept = self._apply_skills(request, work, probabilities)
            parts.append(part)
        if work.tool_ids and work.tools_in is not None:
            request, part, tool_kept = self._apply_tools(request, work, probabilities)
            parts.append(part)
        if work.result_check:
            request, part, result_sufficient = self._apply_result(request, work, probabilities)
            parts.append(part)
        if work.member_ids and not result_sufficient:
            request, part = self._apply_members(request, work, probabilities)
            parts.append(part)
        closed = result_sufficient or any(part.get("kind") == "member" and part.get("kept") == [] for part in parts)
        dispatch = None if closed else self._host_dispatch_part(request)
        if dispatch is not None and not any(part.get("kind") == "tool" for part in parts):
            member_at = next((index for index, part in enumerate(parts) if part.get("kind") == "member"), len(parts))
            parts.insert(member_at, dispatch)
        self._remember_turn(work.turn_key, _TurnFilter(tools=tool_kept, skills=skill_kept))
        if parts:
            self._publish(empty=False, parts=parts)
        return request

    def _apply_result(
        self,
        request: ModelRequest,
        work: _Work,
        probabilities: dict[str, float],
    ) -> tuple[ModelRequest, dict[str, Any], bool]:
        score = probabilities.get("result:sufficient")
        if score is None:
            return request, {"kind": "result", "kept": None}, False
        sufficient = float(score) >= self._config.threshold
        name = (
            ("结果充分, 可以总结" if sufficient else "结果仍需补充")
            if self._chinese
            else ("Sufficient; ready to summarize" if sufficient else "More evidence needed")
        )
        part = {
            "kind": "result",
            "kept": [{"name": name, "score": round(float(score), 2)}],
        }
        if not sufficient:
            return request, part, False
        self._pins[work.thread_key] = _DISPATCH_CLOSED
        hint = (
            "决策模型认为成员结果已经足够. 请直接总结, 不要再调用 ask_agent."
            if self._chinese
            else (
                "The decision model found the member result sufficient. Summarize now and do not call ask_agent again."
            )
        )
        try:
            request = request.override(system_message=append_to_system_message(request.system_message, hint))
        except Exception:
            logger.warning("decision result hint failed", exc_info=True)
        return request, part, True

    def _remember_turn(self, key: str, turn: _TurnFilter) -> None:
        self._turns.pop(key, None)
        self._turns[key] = turn
        while len(self._turns) > 128:
            self._turns.pop(next(iter(self._turns)))

    def _replay(self, request: ModelRequest, turn: _TurnFilter) -> ModelRequest:
        if turn.skills is not None:
            request = _narrow_skills(request, turn.skills)
        if turn.tools is not None:
            request = _narrow_tools(request, turn.tools)
        return request

    def _apply_skills(
        self, request: ModelRequest, work: _Work, probabilities: dict[str, float]
    ) -> tuple[ModelRequest, dict[str, Any], set[str] | None]:
        assert work.skill_ids is not None and work.skill_rows is not None
        scores = _prefixed(probabilities, "skill")
        asked, unasked = _split_asked(work.skill_ids, work.asked_skills)
        chosen = keep_confident(
            scores,
            asked,
            threshold=self._config.threshold,
            limit=self._config.max_selected,
            slack=_KEEP_SLACK,
        )
        if chosen is None:
            return request, self._part("skill", None, scores), None
        kept = set(chosen) | set(unasked)
        return _narrow_skills(request, kept), self._part("skill", chosen, scores), kept

    def _apply_tools(
        self, request: ModelRequest, work: _Work, probabilities: dict[str, float]
    ) -> tuple[ModelRequest, dict[str, Any], set[str] | None]:
        assert work.tool_ids is not None and work.tools_in is not None
        scores = _prefixed(probabilities, "tool")
        asked, unasked = _split_asked(work.tool_ids, work.asked_tools)
        chosen = keep_confident(
            scores,
            asked,
            threshold=self._config.threshold,
            limit=self._config.max_selected,
            slack=_KEEP_SLACK,
        )
        if chosen is None:
            # A real "no" on every asked tool drops the long tail. Missing
            # scores keep the catalog — a partial reply is not a verdict.
            if _fully_scored(scores, asked):
                kept = set(unasked) | _TOOLS_ALWAYS_KEPT
                return _narrow_tools(request, kept), self._part("tool", [], scores), kept
            return request, self._part("tool", None, scores), None
        kept = set(chosen) | set(unasked) | _TOOLS_ALWAYS_KEPT
        return _narrow_tools(request, kept), self._part("tool", chosen, scores), kept

    def _apply_members(
        self, request: ModelRequest, work: _Work, probabilities: dict[str, float]
    ) -> tuple[ModelRequest, dict[str, Any]]:
        assert work.member_ids is not None
        scores = _prefixed(probabilities, "member")
        asked, unasked = _split_asked(work.member_ids, work.asked_members)
        if work.forced_member_ids:
            # Explicit user routing always wins. The decision model still
            # evaluates and displays that choice, but cannot silently reroute.
            return self._pin_members(request, work, list(work.forced_member_ids), scores)
        if unasked or any(item_id not in scores for item_id in asked):
            return request, self._part("member", None, scores, work.member_labels)
        chosen = keep_confident(
            scores,
            asked,
            threshold=self._config.threshold,
            limit=self._config.max_selected,
            slack=_KEEP_SLACK,
        )
        if chosen is None:
            # Wrap-up is an evaluation: a full miss means stop, not "keep everyone".
            if _is_followup(request) and _fully_scored(scores, asked):
                self._pins[work.thread_key] = _DISPATCH_CLOSED
                if self._chinese:
                    hint = "决策模型评估成员结果后认为不必再派工. 请直接收口, 不要再调用 ask_agent."
                else:
                    hint = (
                        "The decision model reviewed the member result and found no further dispatch. "
                        "Wrap up now and do not call ask_agent."
                    )
                try:
                    updated = request.override(system_message=append_to_system_message(request.system_message, hint))
                except Exception:
                    logger.warning("decision wrap-up hint failed", exc_info=True)
                    updated = request
                return updated, self._part("member", [], scores, work.member_labels)
            return request, self._part("member", None, scores, work.member_labels)
        return self._pin_members(request, work, chosen, scores)

    def _pin_members(
        self,
        request: ModelRequest,
        work: _Work,
        chosen: list[str],
        scores: dict[str, float],
    ) -> tuple[ModelRequest, dict[str, Any]]:
        keys: set[str] = set()
        labels: list[str] = []
        for member_id in chosen:
            keys.update(work.member_keys.get(member_id, frozenset()))
            labels.append(work.member_labels.get(member_id, member_id))
        self._pins[work.thread_key] = frozenset(keys)
        if self._chinese:
            hint = "这轮只派给这些成员, 可以同时派给多位: " + "、".join(labels)
        else:
            hint = "Dispatch this turn only to these members; several may run at once: " + ", ".join(labels)
        try:
            updated = request.override(system_message=append_to_system_message(request.system_message, hint))
        except Exception:
            logger.warning("decision member hint failed", exc_info=True)
            updated = request
        return updated, self._part("member", chosen, scores, work.member_labels)

    def _model_label(self) -> str:
        return self._config.model or self._config.provider

    def _publish(self, *, empty: bool, parts: list[dict[str, Any]]) -> None:
        """Hand one decision result to the chat stream. No log line."""
        payload = {
            "kind": "decision",
            "model": self._model_label(),
            "empty": empty,
            "parts": parts,
        }
        _PENDING_DECISION.set(payload)
        try:
            from langgraph.config import get_stream_writer

            writer = get_stream_writer()
        except Exception:
            return
        try:
            writer(payload)
        except Exception:
            return

    def _part(
        self,
        kind: str,
        chosen: list[str] | None,
        scores: dict[str, float],
        labels: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if chosen is None:
            return {"kind": kind, "kept": None}
        items: list[dict[str, Any]] = []
        for item_id in chosen:
            name = labels.get(item_id, item_id) if labels else item_id
            item: dict[str, Any] = {"name": name}
            score = scores.get(item_id)
            if score is not None:
                item["score"] = round(float(score), 2)
            items.append(item)
        return {"kind": kind, "kept": items}

    def _host_dispatch_part(self, request: ModelRequest) -> dict[str, Any] | None:
        """Name the tools a host uses to schedule, without scoring them away."""
        if not self._config.tools:
            return None
        configurable = runtime_config(request).get("configurable") or {}
        if not isinstance(configurable, dict) or not self._async_dispatch(configurable):
            return None
        present = {_tool_name(tool) for tool in list(request.tools or [])}
        kept = [name for name in _HOST_DISPATCH_TOOLS if name in present]
        if "ask_agent" not in kept:
            return None
        return {"kind": "tool", "kept": [{"name": name} for name in kept]}

    def _async_dispatch(self, configurable: dict[str, Any]) -> bool:
        """Team hosts dispatch in the background. One-to-one chats do not.

        A request-scoped ``sync`` always wins, so a member answering inside
        a room cannot pin its own teammates. When the request omits the mode,
        the agent config is the host's async dispatch.
        """
        mode = str(configurable.get("peer_invoke_mode") or "")
        if mode == "async":
            return True
        if mode:
            return False
        agent_id = str(configurable.get("agent_id") or "")
        reader = getattr(self._team, "peer_invoke_mode_for", None)
        if self._team is None or not agent_id or not callable(reader):
            return False
        mode = reader(agent_id)
        return isinstance(mode, str) and mode == "async"

    def _pin(self) -> frozenset[str] | None:
        try:
            from langgraph.config import get_config

            cfg = get_config().get("configurable") or {}
        except Exception:
            return None
        thread_key = str(cfg.get("thread_id") or cfg.get("agent_id") or "")
        return self._pins.get(thread_key)

    def _blocked_ask(self, request: ToolCallRequest) -> ToolMessage | None:
        pin = self._pin()
        if not pin:
            return None
        tool_call = request.tool_call
        if str(tool_call.get("name") or "") != "ask_agent":
            return None
        if pin == _DISPATCH_CLOSED:
            if self._chinese:
                content = "决策模型评估后这轮不再派工. 请直接收口, 不要改派."
            else:
                content = "The decision model closed dispatch for this turn. Wrap up and do not dispatch again."
            return ToolMessage(
                content=content,
                tool_call_id=str(tool_call.get("id") or ""),
                status="error",
            )
        expert = str((tool_call.get("args") or {}).get("expert") or "").strip().lstrip("@").lower()
        if expert and expert in pin:
            return None
        if self._chinese:
            content = "这轮没有把该成员选进派工名单. 请改派已选中的成员, 或先调用 agent_list."
        else:
            content = "That member was not selected for this turn. Dispatch a selected member, or call agent_list."
        return ToolMessage(
            content=content,
            tool_call_id=str(tool_call.get("id") or ""),
            status="error",
        )

    def _filter_agent_list(
        self, request: ToolCallRequest, result: ToolMessage | Command[Any]
    ) -> ToolMessage | Command[Any]:
        pin = self._pin()
        if not pin or not isinstance(result, ToolMessage):
            return result
        if str(request.tool_call.get("name") or "") != "agent_list":
            return result
        content = result.content
        if not isinstance(content, str):
            return result
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return result
        if not isinstance(data, list):
            return result
        kept = []
        for item in data:
            if not isinstance(item, dict):
                continue
            names = {
                str(item.get("agent_id") or "").lower(),
                str(item.get("short_id") or "").lower(),
                str(item.get("name") or "").lower(),
            }
            if names & pin:
                kept.append(item)
        return ToolMessage(
            content=json.dumps(kept, ensure_ascii=False, indent=2),
            tool_call_id=result.tool_call_id,
            status=result.status,
        )


def _allocate(lengths: list[int], limit: int) -> list[int]:
    """Split ``limit`` question slots across groups, then give leftovers back."""
    count = len(lengths)
    if count == 0 or limit <= 0:
        return [0] * count
    share, extra = divmod(limit, count)
    alloc = [min(length, share + (1 if index < extra else 0)) for index, length in enumerate(lengths)]
    leftover = limit - sum(alloc)
    while leftover > 0:
        progressed = False
        for index, length in enumerate(lengths):
            if alloc[index] >= length or leftover <= 0:
                continue
            alloc[index] += 1
            leftover -= 1
            progressed = True
        if not progressed:
            break
    return alloc


def _fit_questions(work: _Work) -> None:
    """Keep each catalog inside the question budget.

    Members are omitted when the roster cannot be asked in full. A partial
    pin would block teammates the model never scored. Skills and tools that
    do not fit stay in the catalog; only scored misses are dropped.
    """
    grouped = {
        "skill": [item for item in work.statements if item[0].startswith("skill:")],
        "tool": [item for item in work.statements if item[0].startswith("tool:")],
        "result": [item for item in work.statements if item[0].startswith("result:")],
        "member": [item for item in work.statements if item[0].startswith("member:")],
    }
    order = [kind for kind in ("result", "skill", "tool", "member") if grouped[kind]]
    if not order:
        return
    alloc = dict(zip(order, _allocate([len(grouped[kind]) for kind in order], _QUESTION_LIMIT), strict=True))
    if "member" in alloc and alloc["member"] < len(grouped["member"]):
        order = [kind for kind in order if kind != "member"]
        grouped["member"] = []
        work.member_ids = None
        if not order:
            work.statements = []
            return
        alloc = dict(zip(order, _allocate([len(grouped[kind]) for kind in order], _QUESTION_LIMIT), strict=True))
    kept: list[tuple[str, str]] = []
    asked: dict[str, list[str]] = {"result": [], "skill": [], "tool": [], "member": []}
    for kind in ("result", "skill", "tool", "member"):
        chosen = grouped[kind][: alloc.get(kind, 0)]
        kept.extend(chosen)
        prefix = kind + ":"
        asked[kind] = [item_id[len(prefix) :] for item_id, _ in chosen]
    work.statements = kept
    work.asked_skills = asked["skill"]
    work.asked_tools = asked["tool"]
    work.asked_members = asked["member"]


def _split_asked(ids: list[str], asked: list[str]) -> tuple[list[str], list[str]]:
    """Ids the model was asked about, and the shortlist entries that did not fit."""
    if not asked:
        return list(ids), []
    asked_set = set(asked)
    return (
        [item_id for item_id in ids if item_id in asked_set],
        [item_id for item_id in ids if item_id not in asked_set],
    )


def _configurable_of(request: ModelRequest) -> dict[str, Any]:
    raw = runtime_config(request).get("configurable") or {}
    return raw if isinstance(raw, dict) else {}


def _is_followup(request: ModelRequest) -> bool:
    """Host wrap-up after a member finishes. Not a new user question."""
    return bool(_configurable_of(request).get("octop_decision_followup"))


def _finished_member(request: ModelRequest) -> str:
    return str(_configurable_of(request).get("octop_decision_finished_member") or "").strip()


def _followup_task(request: ModelRequest) -> str:
    return str(_configurable_of(request).get("octop_decision_task") or "").strip()


def _earlier_user_text(request: ModelRequest) -> str:
    """User text before the latest human message (the wrap-up wakeup)."""
    messages = getattr(request, "messages", None) or []
    seen_latest = False
    for msg in reversed(messages):
        if not isinstance(msg, HumanMessage):
            continue
        if not seen_latest:
            seen_latest = True
            continue
        return _stringify_content(msg.content).strip()
    return ""


def _message_line(msg: Any, *, chinese: bool) -> str:
    text = _stringify_content(getattr(msg, "content", "")).strip()
    if not text:
        return ""
    if isinstance(msg, HumanMessage):
        prefix = "用户: " if chinese else "User: "
        return prefix + text
    if isinstance(msg, AIMessage):
        prefix = "助手: " if chinese else "Assistant: "
        return prefix + text
    return ""


def _fit_lines(lines: list[str], limit: int, *, head: str = "") -> str:
    """Keep ``head`` and the newest line. Older lines fill what is left.

    A line that does not fit is clipped from the start, then anything older
    is dropped. The chat model still sees the full thread; this is only the
    decision ``state`` budget.
    """
    if limit <= 0:
        return ""
    head = _clip(head, min(len(head), max(64, limit // 4))) if head else ""
    body_limit = limit - len(head) - (1 if head else 0)
    if not lines:
        return head
    latest = _clip(lines[-1], body_limit)
    budget = body_limit - len(latest)
    older: list[str] = []
    if budget > 1:
        budget -= 1
        for line in reversed(lines[:-1]):
            if budget <= 0:
                break
            sep = 1 if older else 0
            room = budget - sep
            if room <= 0:
                break
            piece = line if len(line) <= room else _clip(line, room)
            older.append(piece)
            budget -= len(piece) + sep
            if len(line) > room:
                break
        older.reverse()
    parts = [part for part in (head, *older, latest) if part]
    return "\n".join(parts)


def _user_texts(request: ModelRequest) -> list[str]:
    texts: list[str] = []
    for msg in getattr(request, "messages", None) or []:
        if not isinstance(msg, HumanMessage):
            continue
        text = _stringify_content(msg.content).strip()
        if text:
            texts.append(text)
    return texts


def _conversation_lines(request: ModelRequest, *, chinese: bool) -> list[str]:
    lines: list[str] = []
    for msg in getattr(request, "messages", None) or []:
        if isinstance(msg, ToolMessage):
            continue
        line = _message_line(msg, chinese=chinese)
        if line:
            lines.append(line)
    return lines


def _user_history_text(request: ModelRequest) -> str:
    """User turns in this thread. The latest ask stays when the budget is tight."""
    return _fit_lines(_user_texts(request), _STATE_LIMIT)


def _state_text(request: ModelRequest, *, chinese: bool = True) -> str:
    lines = _conversation_lines(request, chinese=chinese)
    head = ""
    if _is_followup(request):
        earlier = _followup_task(request) or _earlier_user_text(request)
        if earlier and not any(earlier in line for line in lines):
            head = earlier
    return _fit_lines(lines, _STATE_LIMIT, head=head) or _clip(_latest_user_text(request), _STATE_LIMIT)


def _thread_key(request: ModelRequest) -> str:
    configurable = runtime_config(request).get("configurable") or {}
    return str(configurable.get("thread_id") or configurable.get("agent_id") or "")


_SKILL_ENTRY_RE = re.compile(r"^- \*\*([^*]+)\*\*:")


def _trim_skill_list(text: str, kept: set[str]) -> str:
    """Drop skill bullets the decision model did not keep.

    SkillsMiddleware writes the full catalog into the system prompt before
    this middleware runs, so narrowing ``skills_metadata`` alone leaves the
    definitions in context.
    """
    start = text.find("**Available Skills:**")
    if start < 0:
        return text
    end = text.find("**How to Use Skills", start)
    if end < 0:
        return text
    lines = text[start:end].split("\n")
    kept_lines = [lines[0]]
    entry: list[str] = []
    name: str | None = None

    def flush() -> None:
        nonlocal entry, name
        if entry and (name is None or name in kept):
            kept_lines.extend(entry)
        entry = []
        name = None

    for line in lines[1:]:
        match = _SKILL_ENTRY_RE.match(line)
        if match:
            flush()
            name = match.group(1).strip()
            entry = [line]
        else:
            entry.append(line)
    flush()
    return text[:start] + "\n".join(kept_lines) + text[end:]


def _map_text(content: Any, edit: Callable[[str], str]) -> Any:
    if isinstance(content, str):
        return edit(content)
    if not isinstance(content, list):
        return content
    changed = False
    blocks: list[Any] = []
    for block in content:
        if isinstance(block, str):
            updated = edit(block)
            changed = changed or updated != block
            blocks.append(updated)
        elif isinstance(block, dict) and block.get("type") == "text":
            text = str(block.get("text") or "")
            updated = edit(text)
            changed = changed or updated != text
            blocks.append({**block, "text": updated})
        else:
            blocks.append(block)
    return blocks if changed else content


def _narrow_skills(request: ModelRequest, kept: set[str]) -> ModelRequest:
    raw = request.state.get("skills_metadata")
    rows = [row for row in raw if isinstance(row, dict)] if isinstance(raw, list) else []
    narrowed = [row for row in rows if not str(row.get("name") or "").strip() or str(row.get("name")) in kept]
    state = cast(AgentState[Any], {**request.state, "skills_metadata": narrowed})
    request = request.override(state=state)
    system = request.system_message
    if system is None:
        return request
    content = _map_text(system.content, lambda text: _trim_skill_list(text, kept))
    if content == system.content:
        return request
    return request.override(system_message=system.model_copy(update={"content": content}))


def _narrow_tools(request: ModelRequest, kept: set[str]) -> ModelRequest:
    filtered = [tool for tool in list(request.tools or []) if not _tool_name(tool) or _tool_name(tool) in kept]
    return request.override(tools=filtered)


def _turn_key(request: ModelRequest) -> str:
    """One user message, stable across the tool loop that follows it."""
    thread = _thread_key(request)
    messages = getattr(request, "messages", None) or []
    for index in range(len(messages) - 1, -1, -1):
        msg = messages[index]
        if isinstance(msg, HumanMessage):
            ident = str(getattr(msg, "id", "") or "") or _clip(_stringify_content(msg.content), 80)
            # The graph may omit message ids. The position is stable while
            # tool/assistant messages are appended, and distinguishes a later
            # user who sends the same text again.
            return f"{thread}\n{index}\n{ident}"
    return thread


def _fully_scored(scores: dict[str, float], ids: list[str]) -> bool:
    return bool(ids) and all(item_id in scores for item_id in ids)


def _prefixed(probabilities: dict[str, float], kind: str) -> dict[str, float]:
    prefix = kind + ":"
    return {key[len(prefix) :]: value for key, value in probabilities.items() if key.startswith(prefix)}


def _named_member_ids(text: str, candidates: list[Candidate]) -> list[str]:
    mentions = [match.group(1).lower() for match in _AGENT_AT_TOKEN_RE.finditer(text)]
    if not mentions:
        return []
    out: list[str] = []
    for item in candidates:
        keys = [key.lower() for key in (item.label.strip(), item.id.strip(), item.id[-6:].strip()) if len(key) >= 2]
        if any(mention in key or key in mention for mention in mentions for key in keys):
            out.append(item.id)
    return out


def _restrict_named_members(
    text: str,
    candidates: list[Candidate],
    labels: dict[str, str],
    keys: dict[str, frozenset[str]],
    *,
    followup: bool,
) -> tuple[
    list[Candidate],
    dict[str, str],
    dict[str, frozenset[str]],
    list[str],
    bool,
]:
    forced = _named_member_ids(text, candidates) if text else []
    if forced:
        forced_set = set(forced)
        chosen = [item for item in candidates if item.id in forced_set]
        chosen_labels = {item_id: label for item_id, label in labels.items() if item_id in forced_set}
        chosen_keys = {item_id: value for item_id, value in keys.items() if item_id in forced_set}
        return chosen, chosen_labels, chosen_keys, [item.id for item in chosen], False
    # An unknown/hidden @mention is still an explicit user choice. Do not let
    # the decision model redirect it to a visible peer.
    unknown_mention = not followup and has_agent_at_mention(text)
    too_few = len(candidates) < (1 if followup else 2)
    return candidates, labels, keys, [], unknown_mention or too_few


__all__ = ["DecisionMiddleware"]
