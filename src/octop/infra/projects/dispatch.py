"""Project task dispatch — plan §T2.5, steps ①-④.

A dispatch turns one task into one agent turn:

① a fresh thread is created for the assignee (the same thing
   ``POST /api/agents/{agent_id}/threads`` does, without going through HTTP),
② the task is rendered as plain text (:func:`build_dispatch_prompt`),
③ the turn runs under the target session's serialization lock,
④ for ``assignee_type=team`` the turn runs the **team host** with its runtime
   stamped onto async ``ask_agent``, so members are reached through the room
   instead of a one-shot tool return.

Steps ⑤/⑥ (``project_tasks.thread_id`` and the ``task.dispatched`` timeline row)
stay in :mod:`octop.infra.projects.service` with the other task writes.

The turn itself is **not** implemented here: :func:`octop.infra.cron.delivery.run_agent_turn`
is the path extracted from cron delivery, reused verbatim.

**Not verified end to end.** The machine this was developed on has no LLM provider
and no configured agent, so no real turn was ever driven through
:func:`run_dispatch_turn`: the registry is stubbed in every test. Whether the team
host's ``ask_agent`` really opens the room, and whether the members' replies fan
back in, is therefore unproven — that needs a live provider plus a real team.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from octop.infra.cron.delivery import run_agent_turn
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.threads import ThreadRegistry

if TYPE_CHECKING:
    from octop.infra.agents.manager import AgentManager
    from octop.infra.db.repos.project_tasks import ProjectTaskRow
    from octop.infra.db.repos.projects import ProjectRow
    from octop.infra.db.services import RepoBundle
    from octop.infra.gateway.gateway import Gateway

#: Only these assignees have a runtime that can start a turn (§T2.5 校验).
DISPATCH_ASSIGNEE_TYPES: tuple[str, ...] = ("agent", "team")

#: ``chat_type`` of a dispatch session (SPEC B30 ①) — never ``dm``.
DISPATCH_CHAT_TYPE = "dispatch"

#: The shape of a user's private DM key (``<agent>:dashboard:<user_id>:dm``).
#: A dispatch key that matches is refused instead of rebound (SPEC B30 ④).
_USER_DM_SESSION_KEY = re.compile(r":dashboard:\d+:dm$")

#: Plan §4.4 stores acceptance criteria in this fixed section of
#: ``project_tasks.description`` instead of a schema column, so the dispatch
#: message always renders the heading the plan/AC-09 names.
ACCEPTANCE_HEADING = "验收标准"
_ACCEPTANCE_SECTION = re.compile(r"^[ \t]*#{1,6}[ \t]*验收标准[ \t]*$", re.MULTILINE)

# Deliberately not i18n keys: the plan fixes this wording (`## 验收标准`), and the
# text is a briefing for the assignee rather than server-owned user-facing copy.
_NO_DESCRIPTION = "（无描述）"
_NO_ACCEPTANCE = "（未填写验收标准）"


def split_acceptance(description: str) -> tuple[str, str]:
    """Split a task description into ``(body, acceptance criteria)``.

    The acceptance section is everything after the first ``## 验收标准`` heading;
    a description without one yields an empty criteria string.
    """
    text = description or ""
    match = _ACCEPTANCE_SECTION.search(text)
    if match is None:
        return text.strip(), ""
    return text[: match.start()].strip(), text[match.end() :].strip()


def task_link(project_id: str, task_id: str) -> str:
    """Dashboard deep link for one task.

    Relative on purpose: Octop has no configured public base URL, and the link is
    read by an agent (and by the user inside the thread), not rendered as HTML.
    """
    return f"/projects/{project_id}?task={task_id}"


def build_dispatch_prompt(
    *,
    project_name: str,
    task_title: str,
    description: str,
    link: str,
) -> str:
    """Assemble the plain-text dispatch message (plan §T2.5 ②, AC-09).

    Pure — no DB, no runtime — which is what keeps AC-09 testable on a machine
    with no LLM provider.
    """
    body, acceptance = split_acceptance(description)
    return (
        f"【项目派工】{project_name}\n"
        f"\n"
        f"## 任务标题\n"
        f"{task_title}\n"
        f"\n"
        f"## 任务描述\n"
        f"{body or _NO_DESCRIPTION}\n"
        f"\n"
        f"## {ACCEPTANCE_HEADING}\n"
        f"{acceptance or _NO_ACCEPTANCE}\n"
        f"\n"
        f"任务链接：{link}"
    )


def require_dispatchable(task: ProjectTaskRow) -> str:
    """Return the task's assignee id, or reject a task that cannot be dispatched.

    A human assignee (or no assignee at all) is a caller error, not a server
    fault: the refusal is a ``409 PROJECT_TASK_DISPATCH_INVALID`` envelope, never
    an unhandled ``500`` (FIND-2 / PLAN.md §2.2).
    """
    assignee_type = (task.assignee_type or "").strip()
    if assignee_type not in DISPATCH_ASSIGNEE_TYPES:
        raise OctopError(
            ErrorCode.PROJECT_TASK_DISPATCH_INVALID,
            "task assignee_type must be one of "
            f"{', '.join(DISPATCH_ASSIGNEE_TYPES)} to dispatch (got {assignee_type or 'none'!r})",
        )
    assignee_id = (task.assignee_id or "").strip()
    if not assignee_id:
        raise OctopError(
            ErrorCode.PROJECT_TASK_DISPATCH_INVALID,
            "task has no assignee_id to dispatch",
        )
    return assignee_id


def dispatch_session_key(*, agent_id: str, dispatch_id: str) -> str:
    """Session key one dispatch turn runs under (SPEC B30 ①).

    Deliberately **not** the dispatcher's private DM session key (the registry's
    ``dashboard`` DM key): binding the dispatch thread to that key **rewrites the
    user's own session in place** — one dispatch hijacks the conversation. A
    dispatch gets a key of its own instead: dispatch-scoped (``chat_type`` is
    :data:`DISPATCH_CHAT_TYPE`, never ``dm``) and shaped so it can never equal a
    user DM key.

    *dispatch_id* names the dispatch — the project task today, the run/role for
    run and phase dispatch — and must not contain ``":"`` (keys are split on it).
    """
    return ThreadRegistry.make_key(
        agent_id=agent_id,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
        channel_subject_id=dispatch_id,
        channel_chat_type=DISPATCH_CHAT_TYPE,
    )


def require_dispatch_session_key(session_key: str) -> str:
    """Return *session_key* unless it is a user DM key, which is refused (SPEC B30 ④).

    The guard for a caller-supplied dispatch key (run / phase dispatch pass their
    own). The key of a user's private DM session is already bound to that user's
    thread, so a dispatch may not take it over: the refusal reuses the plan's
    same-key conflict, ``409 TEAM_RUN_CONFLICT`` with
    ``details["reason"] == "session_key_already_bound"`` — not a new error code.
    """
    if _USER_DM_SESSION_KEY.search(session_key):
        raise OctopError(
            ErrorCode.TEAM_RUN_CONFLICT,
            f"session key {session_key!r} is already bound to a user DM session",
            details={"reason": "session_key_already_bound"},
        )
    return session_key


class _TeamRoomBridge:
    """R17 facade: the only place the dispatch path touches ``infra/agents/teams``.

    Two calls make up the whole team surface here — "is this assignee a team host"
    and "stamp the host runtime onto the request". An upstream signature change to
    the team room therefore edits this class alone.
    """

    def __init__(self, *, agent_manager: AgentManager, gateway: Gateway) -> None:
        self._agent_manager = agent_manager
        self._gateway = gateway

    def is_team_host(self, agent_id: str) -> bool:
        from octop.infra.agents.teams import is_team_agent

        return is_team_agent(self._agent_manager.get_row(agent_id))

    def stamp_host_runtime(self, request: dict[str, Any], agent_id: str) -> None:
        """Plan §T2.5 ④: a team host must start a real turn on the room.

        ``TeamManager.stamp_host_runtime`` forces ``peer_invoke_mode=async``, which
        is what makes the host's ``ask_agent`` open the team room and fan member
        speech back, instead of a synchronous one-shot call. Non-team assignees are
        left untouched.
        """
        if not self.is_team_host(agent_id):
            return
        self._gateway.processor.teams.stamp_host_runtime(request, agent_id)


async def run_dispatch_turn(
    *,
    repos: RepoBundle,
    agent_manager: AgentManager,
    gateway: Gateway,
    project: ProjectRow,
    task: ProjectTaskRow,
    dispatcher_user_id: int,
    session_key: str | None = None,
) -> str:
    """Run steps ①-④ of plan §T2.5 and return the thread the turn ran in.

    *session_key* is the key to run under — run / phase dispatch passes its own
    run-scoped one. Omitted, the dispatch gets its own key for *task*; either way
    a user DM key is refused (``TEAM_RUN_CONFLICT``, SPEC B30).

    Raises before creating anything when the task cannot be dispatched
    (``PROJECT_TASK_DISPATCH_INVALID``), or when the assignee is missing / not
    running (``AGENT_NOT_FOUND`` / ``AGENT_NOT_RUNNING``, straight from the registry).
    """
    assignee_id = require_dispatchable(task)
    # Existence + running state of the assignee, with the registry's own codes.
    agent_manager.get_agent(assignee_id)
    bridge = _TeamRoomBridge(agent_manager=agent_manager, gateway=gateway)

    # ① A fresh thread for this dispatch, on a dispatch-only session key (SPEC B30):
    #    the dispatcher's private DM session key belongs to their own conversation,
    #    and the `rebind` below would rewrite that session's thread in place. A
    #    caller that supplies its own run/phase key still cannot supply a DM key.
    session_key = (
        require_dispatch_session_key(session_key)
        if session_key
        else dispatch_session_key(agent_id=assignee_id, dispatch_id=task.id)
    )
    thread_id = gateway.thread_registry.create_thread(
        agent_id=assignee_id,
        user_id=dispatcher_user_id,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
        session_key=session_key,
        title=task.title,
    )
    # `create_thread` deliberately does not rebind the session (the registry's own
    # docstring). Dispatch needs the session row to hold the lock and to mint the
    # request, so create that row here — with the dispatch chat type, which a
    # `rebind` of a brand-new key would default to `dm`.
    if repos.session_repo.get(session_key) is None:
        repos.session_repo.upsert(
            session_key=session_key,
            agent_id=assignee_id,
            user_id=dispatcher_user_id,
            channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
            chat_type=DISPATCH_CHAT_TYPE,
            thread_id=thread_id,
        )
    # An existing row keeps its own chat type; `rebind` only moves the binding.
    await gateway.thread_registry.rebind(
        session_key=session_key,
        thread_id=thread_id,
        agent_id=assignee_id,
    )
    session = gateway.require_session(assignee_id, session_key)

    # ② Plain-text task context; ③/④ one turn under the session lock, with the
    #    team-host runtime stamped for a team assignee.
    prompt = build_dispatch_prompt(
        project_name=project.name,
        task_title=task.title,
        description=task.description,
        link=task_link(project.id, task.id),
    )

    async def _locked() -> None:
        await run_agent_turn(
            agent_manager=agent_manager,
            repos=repos,
            agent_id=assignee_id,
            session=session,
            prompt=prompt,
            usage_source="project",
            turn_label="project dispatch",
            prepare_request=lambda request: bridge.stamp_host_runtime(request, assignee_id),
        )

    await gateway.run_in_session(assignee_id, session_key, _locked)
    return thread_id


__all__ = [
    "ACCEPTANCE_HEADING",
    "DISPATCH_ASSIGNEE_TYPES",
    "DISPATCH_CHAT_TYPE",
    "build_dispatch_prompt",
    "dispatch_session_key",
    "require_dispatch_session_key",
    "require_dispatchable",
    "run_dispatch_turn",
    "split_acceptance",
    "task_link",
]
