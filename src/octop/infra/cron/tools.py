"""Built-in LangChain tools for agent-managed cron jobs."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Annotated, Any

from langchain_core.tools import StructuredTool
from langgraph.config import get_config
from pydantic import Field

from octop.infra.cron.manager import CronCreateSpec
from octop.infra.cron.session_target import thread_target_key
from octop.infra.cron.task_type import (
    CRON_NAME_MAX_LEN,
    require_cron_name,
    require_cron_prompt,
    require_cron_task_type,
)
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.utils.ulid import new_cron_id

if TYPE_CHECKING:
    from octop.infra.cron.manager import CronManager
    from octop.infra.db.repos.cron import CronJobRow

_TRIGGER_HELP = (
    "Schedule spec: cron:<5-field expr> (e.g. cron:0 9 * * *), "
    "interval:<seconds> (e.g. interval:3600), date:<ISO8601> (runs once, then the job "
    "disables itself whether the run succeeds or fails), or "
    "agently:<connector instance id> for new mail from a visible Agent Mail connector. "
    "The mail source runs message +watch in the background; never poll mail with the LLM."
)

_TASK_TYPE_HELP = (
    "Delivery mode. Default 'text'. "
    "Use 'text' when the user wants a fixed reminder/notification — prompt is pushed verbatim "
    "(e.g. drink water, stand-up, daily greeting). "
    "Use 'agent' only when each run must query, analyze, or summarize fresh data."
)

_SESSION_TARGET_HELP = (
    "Where the run lands when fresh_thread is false. "
    "'latest' (default): each run uses the most recent conversation on the current channel. "
    "'history': stay on one conversation. Pass thread_id, or omit it to pin the current conversation. "
    "Ignored when fresh_thread is true, which starts a new conversation every run."
)

_CRONJOB_CREATE_DESC = (
    "Create a scheduled cron job on the current channel (QQ/WeChat/dashboard/…). "
    "name is required: a short label for the job list. "
    f"session_target: {_SESSION_TARGET_HELP} "
    f"task_type: {_TASK_TYPE_HELP} "
    "Examples: 'remind me to drink water at 14:00 daily' → "
    "name='Daily water reminder', task_type=text, prompt='Time to drink water', session_target=latest; "
    "'summarize my inbox every morning into this chat' → "
    "name='Morning inbox summary', task_type=agent, session_target=history. "
    f"trigger: {_TRIGGER_HELP}"
)

_CRONJOB_UPDATE_DESC = (
    "Update an existing cron job (trigger, prompt, enabled, task_type, session_target, …). "
    f"session_target: {_SESSION_TARGET_HELP} "
    f"task_type: {_TASK_TYPE_HELP} "
    f"trigger: {_TRIGGER_HELP}"
)


def _tool_ctx() -> tuple[str, int, str]:
    cfg = get_config().get("configurable") or {}
    agent_id = cfg.get("agent_id")
    user_raw = cfg.get("user")
    if not agent_id:
        raise ValueError("missing configurable.agent_id")
    if user_raw is None:
        raise ValueError("missing configurable.user")
    user_id = int(user_raw)
    session_key = cfg.get("session_key")
    if not session_key:
        session_key = ThreadRegistry.dashboard_key(agent_id=str(agent_id), user_id=user_id)
    return str(agent_id), user_id, str(session_key)


def _user_owns_agent(mgr: CronManager, agent_id: str, user_id: int) -> bool:
    row = mgr._repos.agent_repo.get(agent_id)
    return row is not None and row.user_id == user_id


def _require_agent_owner(mgr: CronManager, agent_id: str, user_id: int) -> None:
    if not _user_owns_agent(mgr, agent_id, user_id):
        raise ValueError("cron jobs can only be managed by the expert owner")


def _get_owned(mgr: CronManager, cron_id: str, agent_id: str, user_id: int) -> CronJobRow:
    _require_agent_owner(mgr, agent_id, user_id)
    row = mgr.get(cron_id)
    if row is None or row.agent_id != agent_id:
        raise ValueError(f"cron job not found: {cron_id}")
    return row


def _stored_session_key(
    *,
    channel_session_key: str,
    fresh_thread: bool,
    session_target: str | None,
    thread_id: str | None,
) -> str:
    """Channel key for latest runs, or ``thread:{id}`` for a history pin."""
    target = (session_target or "latest").strip().lower()
    if fresh_thread or target == "latest":
        return channel_session_key
    if target != "history":
        raise ValueError("session_target must be 'latest' or 'history'")
    pinned = (thread_id or "").strip()
    if not pinned:
        cfg = get_config().get("configurable") or {}
        pinned = str(cfg.get("thread_id") or "").strip()
    if not pinned:
        raise ValueError("history session_target requires thread_id")
    return thread_target_key(pinned)


def _ok(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _err(exc: Exception) -> str:
    return json.dumps({"error": str(exc)}, ensure_ascii=False)


def build_cronjob_tools(cron_manager: CronManager) -> list[StructuredTool]:
    """Return built-in cron management tools (not MCP — wired via HarnessAgentConfig.tools)."""
    mgr = cron_manager

    async def cronjob_list(include_disabled: bool = True) -> str:
        try:
            agent_id, user_id, _session_key = _tool_ctx()
            if not _user_owns_agent(mgr, agent_id, user_id):
                return _ok([])
            rows = mgr.list_by_agent(agent_id, include_disabled=include_disabled)
            return _ok([r.to_public_dict() for r in rows])
        except Exception as exc:
            return _err(exc)

    async def cronjob_get(cron_id: str) -> str:
        try:
            agent_id, user_id, _session_key = _tool_ctx()
            row = _get_owned(mgr, cron_id, agent_id, user_id)
            return _ok(row.to_public_dict())
        except Exception as exc:
            return _err(exc)

    async def cronjob_create(
        trigger: Annotated[
            str,
            Field(description=f"When to run. {_TRIGGER_HELP}"),
        ],
        prompt: Annotated[
            str,
            Field(
                description=(
                    "For task_type=text: the exact message to push. "
                    "For task_type=agent: the instruction sent to the agent each run."
                ),
            ),
        ],
        name: Annotated[
            str,
            Field(
                description=(
                    "Required short display name shown in the job list "
                    f"(max {CRON_NAME_MAX_LEN} characters). "
                    "Summarize the user's request, e.g. 'Daily water reminder'."
                ),
            ),
        ],
        fresh_thread: Annotated[
            bool,
            Field(
                description="If true, start a new conversation before each run. Ignores session_target."
            ),
        ] = False,
        session_target: Annotated[
            str,
            Field(description=_SESSION_TARGET_HELP),
        ] = "latest",
        thread_id: Annotated[
            str | None,
            Field(
                description=(
                    "Historical conversation to pin when session_target is 'history'. "
                    "Omit to pin the current conversation."
                ),
            ),
        ] = None,
        enabled: Annotated[
            bool,
            Field(description="Whether the job is active immediately after creation."),
        ] = True,
        task_type: Annotated[
            str,
            Field(description=_TASK_TYPE_HELP),
        ] = "text",
    ) -> str:
        try:
            agent_id, user_id, channel_key = _tool_ctx()
            _require_agent_owner(mgr, agent_id, user_id)
            cron_id = new_cron_id()
            cleaned_prompt = require_cron_prompt(prompt)
            spec = CronCreateSpec(
                cron_id=cron_id,
                agent_id=agent_id,
                user_id=user_id,
                name=require_cron_name(name, prompt=cleaned_prompt, cron_id=cron_id),
                trigger=trigger,
                prompt=cleaned_prompt,
                fresh_thread=fresh_thread,
                session_key=_stored_session_key(
                    channel_session_key=channel_key,
                    fresh_thread=fresh_thread,
                    session_target=session_target,
                    thread_id=thread_id,
                ),
                enabled=enabled,
                task_type=require_cron_task_type(task_type),
            )
            row = await mgr.create(spec)
            return _ok(row.to_public_dict())
        except Exception as exc:
            return _err(exc)

    async def cronjob_update(
        cron_id: str,
        name: Annotated[str | None, Field(description="New display name.")] = None,
        trigger: Annotated[str | None, Field(description=f"New schedule. {_TRIGGER_HELP}")] = None,
        prompt: Annotated[
            str | None,
            Field(description="New prompt / message text."),
        ] = None,
        fresh_thread: bool | None = None,
        session_target: Annotated[
            str | None,
            Field(description=_SESSION_TARGET_HELP),
        ] = None,
        thread_id: Annotated[
            str | None,
            Field(description="Historical conversation to pin when session_target is 'history'."),
        ] = None,
        enabled: bool | None = None,
        task_type: Annotated[str | None, Field(description=_TASK_TYPE_HELP)] = None,
    ) -> str:
        try:
            agent_id, user_id, channel_key = _tool_ctx()
            existing = _get_owned(mgr, cron_id, agent_id, user_id)
            cleaned_prompt = require_cron_prompt(prompt) if prompt is not None else None
            stored_session: str | None = None
            if fresh_thread or session_target is not None or (thread_id or "").strip():
                stored_session = _stored_session_key(
                    channel_session_key=channel_key,
                    fresh_thread=bool(fresh_thread),
                    session_target=session_target
                    or ("history" if (thread_id or "").strip() else "latest"),
                    thread_id=thread_id,
                )
            row = await mgr.update(
                cron_id,
                name=(
                    require_cron_name(
                        name,
                        prompt=cleaned_prompt or existing.prompt,
                        cron_id=cron_id,
                    )
                    if name is not None
                    else None
                ),
                trigger=trigger,
                prompt=cleaned_prompt,
                session_key=stored_session,
                fresh_thread=fresh_thread,
                enabled=int(enabled) if enabled is not None else None,
                task_type=require_cron_task_type(task_type) if task_type is not None else None,
            )
            return _ok(row.to_public_dict())
        except Exception as exc:
            return _err(exc)

    async def cronjob_delete(cron_id: str) -> str:
        try:
            agent_id, user_id, _session_key = _tool_ctx()
            _get_owned(mgr, cron_id, agent_id, user_id)
            await mgr.delete(cron_id)
            return _ok({"deleted": cron_id})
        except Exception as exc:
            return _err(exc)

    async def cronjob_run_now(cron_id: str) -> str:
        try:
            agent_id, user_id, _session_key = _tool_ctx()
            _get_owned(mgr, cron_id, agent_id, user_id)
            await mgr.run_now(cron_id)
            return _ok({"triggered": cron_id})
        except Exception as exc:
            return _err(exc)

    return [
        StructuredTool.from_function(
            coroutine=cronjob_list,
            name="cronjob_list",
            description="List scheduled cron jobs for the current agent.",
        ),
        StructuredTool.from_function(
            coroutine=cronjob_get,
            name="cronjob_get",
            description="Get details of one cron job by id.",
        ),
        StructuredTool.from_function(
            coroutine=cronjob_create,
            name="cronjob_create",
            description=_CRONJOB_CREATE_DESC,
        ),
        StructuredTool.from_function(
            coroutine=cronjob_update,
            name="cronjob_update",
            description=_CRONJOB_UPDATE_DESC,
        ),
        StructuredTool.from_function(
            coroutine=cronjob_delete,
            name="cronjob_delete",
            description="Delete a cron job by id.",
        ),
        StructuredTool.from_function(
            coroutine=cronjob_run_now,
            name="cronjob_run_now",
            description="Trigger one immediate run of a cron job.",
        ),
    ]
