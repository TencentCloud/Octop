"""Project domain service — lifecycle, knowledge-base binding, permissions.

Three responsibilities beyond the repos (plan T2.1):

1. **Knowledge-base lifecycle.** A project owns one KB whose name mirrors the
   project name. Creation is a multi-step, cross-repo flow, and the repos each
   open their own transaction — there is no shared transaction to roll back.
   Every failure therefore runs an explicit **compensating delete** so we never
   leave a project without its KB, or a KB without its project.
2. **State machines.** Projects: ``draft -> active -> (paused|completed|cancelled)
   -> archived`` (PLAN.md §3.1); ``archived`` is terminal and makes the project
   read-only. Tasks: seven states with ``planning`` as the entry state (§1.2).
3. **Permission matrix** (plan §4.6) behind :meth:`ProjectService.assert_project_role`.

Task dispatch (plan T2.5) hangs off the same service — :meth:`ProjectService.dispatch_task`
owns the task write and the timeline row, while the turn itself lives in
:mod:`octop.infra.projects.dispatch` and reuses cron's extracted delivery path.

Membership is the only way in: a platform admin who is not a project member is
rejected like anyone else. The coarse ``projects`` permission key gates "may use
the project feature"; the ``project_members`` join gates the data.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Protocol

from octop.infra.db.repos._base import UNSET
from octop.infra.db.repos.project_tasks import (
    TASK_STATUSES,
    TIMELINE_TASK_ASSIGNED,
    TIMELINE_TASK_CREATED,
    TIMELINE_TASK_DELETED,
    TIMELINE_TASK_DISPATCHED,
    TIMELINE_TASK_STATUS_CHANGED,
    TIMELINE_TASK_UPDATED,
    ProjectTaskRow,
    TimelineEventRow,
    actor_ref,
)
from octop.infra.db.repos.projects import (
    MEMBER_SUBJECT_USER,
    PROJECT_ROLES,
    PROJECT_STATUSES,
    ProjectMemberRow,
    ProjectRow,
)
from octop.infra.db.services import SharedServices
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.knowledge.gate import get_capability
from octop.infra.knowledge.service import MAX_BASES_PER_OWNER, KnowledgeService
from octop.infra.projects.dispatch import run_dispatch_turn
from octop.infra.users.permissions import user_has_permission

if TYPE_CHECKING:
    from octop.infra.agents.manager import AgentManager
    from octop.infra.gateway.gateway import Gateway

logger = logging.getLogger(__name__)

# ── permission levels (§4.6), weakest first ──────────────────────────────────
PROJECT_READ = "read"
PROJECT_WRITE = "write"
PROJECT_CONFIRM = "confirm"
PROJECT_MANAGE_MEMBERS = "manage_members"
#: Configuration writes (instruction / connectors / skills / cron) — PLAN.md §6.
#: Deliberately a **peer** of ``write``: configuration decides what the project's
#: agents may reach, so a member who may edit the goal must not get it, and the
#: four config write routes must never be guarded by ``write`` alone.
PROJECT_MANAGE_CONFIG = "manage_config"
PROJECT_ARCHIVE = "archive"

PROJECT_ACTIONS: tuple[str, ...] = (
    PROJECT_READ,
    PROJECT_WRITE,
    PROJECT_CONFIRM,
    PROJECT_MANAGE_MEMBERS,
    PROJECT_MANAGE_CONFIG,
    PROJECT_ARCHIVE,
)

#: Which levels each role satisfies. This is a plain role -> action **lookup**;
#: there is no implication between actions (PLAN.md §3.3 / R18), so
#: ``manage_config`` is granted explicitly and never derived from ``write``.
#: Note ``admin`` deliberately lacks ``archive`` — §4.6 gives archive/delete to
#: the owner alone.
_ROLE_LEVELS: dict[str, frozenset[str]] = {
    "owner": frozenset(PROJECT_ACTIONS),
    "admin": frozenset(
        {
            PROJECT_READ,
            PROJECT_WRITE,
            PROJECT_CONFIRM,
            PROJECT_MANAGE_MEMBERS,
            PROJECT_MANAGE_CONFIG,
        }
    ),
    "member": frozenset({PROJECT_READ, PROJECT_WRITE}),
    "viewer": frozenset({PROJECT_READ}),
}

#: Allowed project status transitions (PLAN.md §3.1). ``archived`` is terminal;
#: ``draft -> completed`` is deliberately unreachable (activate first), while a
#: completed / cancelled project can be reopened through ``active``.
_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"active", "cancelled"}),
    "active": frozenset({"paused", "completed", "cancelled", "archived"}),
    "paused": frozenset({"active", "completed", "cancelled", "archived"}),
    "completed": frozenset({"active", "archived"}),
    "cancelled": frozenset({"active", "archived"}),
    "archived": frozenset(),
}

#: Allowed task status transitions (PLAN.md §1.2, frozen).
#:
#: ``planning`` is the entry state: it can leave for ``todo`` (scheduled) or
#: ``cancelled``, and the only other way in is ``todo -> planning`` — a task that
#: has started work must not be able to hide its progress. The six pre-existing
#: states keep their adjacency verbatim.
_TASK_TRANSITIONS: dict[str, frozenset[str]] = {
    "planning": frozenset({"todo", "cancelled"}),
    "todo": frozenset({"planning", "doing", "blocked", "cancelled"}),
    "doing": frozenset({"todo", "review", "done", "blocked", "cancelled"}),
    "review": frozenset({"doing", "done", "blocked", "cancelled"}),
    "blocked": frozenset({"todo", "doing", "cancelled"}),
    "done": frozenset({"doing"}),
    "cancelled": frozenset(),
}

#: Task dates are unix seconds inside this half-open range (2100-01-01 UTC), which
#: also rejects the common milliseconds mistake (~1.7e12) — PLAN.md §5.
_TASK_DATE_MIN = 1
_TASK_DATE_MAX = 4102444800


class ProjectActor(Protocol):
    """The slice of a user row this service needs."""

    id: int

    @property
    def is_admin(self) -> bool: ...

    permissions: list[str]


def _forbidden(message: str) -> OctopError:
    """No access to the project at all (not a member, archived, feature off)."""
    return OctopError(ErrorCode.PROJECT_FORBIDDEN, message)


def _role_forbidden(message: str) -> OctopError:
    """A member, but the role is too weak for the requested action (§4.6)."""
    return OctopError(ErrorCode.PROJECT_ROLE_FORBIDDEN, message)


def _member_invalid(message: str) -> OctopError:
    """A membership change that would break a project invariant."""
    return OctopError(ErrorCode.PROJECT_MEMBER_INVALID, message)


def _project_status_invalid(message: str) -> OctopError:
    return OctopError(ErrorCode.PROJECT_STATUS_INVALID, message)


def _task_status_invalid(message: str) -> OctopError:
    return OctopError(ErrorCode.PROJECT_TASK_STATUS_INVALID, message)


def _task_date_invalid(message: str) -> OctopError:
    return OctopError(ErrorCode.PROJECT_TASK_DATE_INVALID, message)


def _check_task_dates(start_at: int | None, due_at: int | None) -> None:
    """Reject unusable task dates (PLAN.md §5): range first, then ordering.

    The check lives here rather than in a DB ``CHECK`` because SQLite cannot add
    one by ``ALTER`` and the repo deliberately carries no validation.
    """
    for label, value in (("start_at", start_at), ("due_at", due_at)):
        if value is not None and not (_TASK_DATE_MIN <= value < _TASK_DATE_MAX):
            raise _task_date_invalid(f"task {label} is not a valid unix timestamp")
    if start_at is not None and due_at is not None and start_at > due_at:
        raise _task_date_invalid("task start_at must not be after due_at")


class ProjectService:
    def __init__(
        self,
        services: SharedServices,
        *,
        agent_manager: AgentManager | None = None,
        gateway: Gateway | None = None,
    ) -> None:
        self._services = services
        self._projects = services.project_repo
        self._members = services.project_member_repo
        self._tasks = services.project_task_repo
        self._timeline = services.timeline_repo
        # Runtime handles used by task dispatch only (plan T2.5); they are optional
        # because the CRUD / board surface needs neither agent registry nor gateway.
        self._agent_manager = agent_manager
        self._gateway = gateway
        # Plain attribute (not a property) so tests can inject a failing KB
        # service and drive the compensating-delete branch.
        self._knowledge = KnowledgeService(services)

    # ── reads ────────────────────────────────────────────────────────────────

    def list_projects(self, *, user: ProjectActor) -> list[ProjectRow]:
        self._assert_feature_enabled(user)
        return self._projects.list_for_user(user.id)

    def get_project(self, project_id: str, *, user: ProjectActor) -> ProjectRow:
        project = self._require_project(project_id)
        self.assert_project_role(project.id, user=user, required=PROJECT_READ)
        return project

    def list_members(self, project_id: str, *, user: ProjectActor) -> list[ProjectMemberRow]:
        self.assert_project_role(project_id, user=user, required=PROJECT_READ)
        return self._members.list_by_project(project_id)

    def list_members_with_names(
        self, project_id: str, *, user: ProjectActor
    ) -> list[tuple[ProjectMemberRow, str | None]]:
        """Members paired with their display name (PLAN.md §2.2).

        ``agent`` → ``agents.name``; ``user`` → ``users.display_name`` then
        ``username``; anything unresolvable (missing row, blank name, or a
        ``team`` subject with no name source in this build) → ``None``. The caller
        falls back to ``subject_id``; nothing here raises or turns into a 500.
        """
        rows = self.list_members(project_id, user=user)
        return [(row, self._resolve_subject_name(row.subject_type, row.subject_id)) for row in rows]

    def _resolve_subject_name(self, subject_type: str, subject_id: str) -> str | None:
        if subject_type in ("agent", "team"):
            # A team *is* an ``agents`` row with ``kind='team'`` (verified on the live
            # DB: ``agents.kind`` = expert×2 + team×1), so both subject types resolve
            # through the same read path. An id that is not in ``agents`` still
            # yields ``None`` — identical to the previous behaviour, never worse.
            agent = self._services.agent_repo.get(subject_id)
            return (agent.name or None) if agent is not None else None
        if subject_type == "user":
            try:
                user_id = int(subject_id)
            except (TypeError, ValueError):
                return None
            row = self._services.user_repo.get(user_id)
            if row is None:
                return None
            return (getattr(row, "display_name", None) or "").strip() or row.username or None
        return None

    # ── permissions (§4.6) ───────────────────────────────────────────────────

    def assert_project_role(
        self,
        project_id: str,
        *,
        user: ProjectActor,
        required: str,
    ) -> str:
        """Return the caller's project role, or raise ``FORBIDDEN``.

        Non-members are always rejected — ``user.is_admin`` does **not** bypass
        this, because project data is guarded by membership rather than by the
        coarse ``projects`` permission key.
        """
        if required not in PROJECT_ACTIONS:
            raise ValueError(f"unknown project action: {required}")
        project = self._require_project(project_id)
        role = self._role_of(project, user)
        if role is None:
            raise _forbidden("You are not a member of this project.")
        if project.status == "archived" and required != PROJECT_READ:
            raise _forbidden("This project is archived and can no longer be changed.")
        if required not in _ROLE_LEVELS[role]:
            raise _role_forbidden(
                f"Your role in this project ({role}) cannot perform '{required}'."
            )
        return role

    def role_of(self, project_id: str, *, user: ProjectActor) -> str | None:
        return self._role_of(self._require_project(project_id), user)

    # ── create (plan T2.1 ①) ─────────────────────────────────────────────────

    def create_project(
        self,
        *,
        owner_user: ProjectActor,
        name: str,
        goal: str = "",
        status: str | None = None,
        start_at: int | None = None,
        due_at: int | None = None,
    ) -> ProjectRow:
        """Create a project, binding a knowledge base when one can be created.

        ``status`` is an **initial value assignment, not a transition**: the
        creation dialog offers all six states (SPEC S-10), so ``_TRANSITIONS`` is
        not consulted here. ``None`` keeps the repo default (``draft``); anything
        outside ``PROJECT_STATUSES`` is a 409 rather than a silent drop.

        Steps (each with an explicit failure branch):

        ⓪ preconditions — no side effects, so an unactionable ⓪ leaves nothing behind
        ① ``projects`` row
        ② owner membership row
        ③ knowledge base            (only when the knowledge feature is usable)
        ④ write ``kb_id`` back onto the project

        A failure in ③ or ④ deletes whatever the earlier steps created, then
        raises ``PROJECT_KB_BIND_FAILED``.

        **When the knowledge feature is not usable** (feature off, or no usable
        embedding model) the project is still created with ``kb_id = NULL``.
        Making the KB mandatory would mean a fresh install cannot create a
        project at all until an embedding model is configured, and the plan's
        own T3.4 note ("归档只在 ``kb_id IS NOT NULL`` 时执行") presupposes the
        NULL case. The hard compensating-delete path is kept for the case that
        matters: the feature *is* ready, so a failure there is a real failure
        rather than a missing prerequisite.
        """
        self._assert_feature_enabled(owner_user)
        name = name.strip()
        if not name:
            raise ValueError("project name is required")
        if status is not None and status not in PROJECT_STATUSES:
            raise _project_status_invalid(f"Unknown project status: '{status}'.")

        bind_kb = self._knowledge_usable()
        if bind_kb:
            # ⓪ No side effects yet, so these surface the KB error codes directly —
            #    they are actionable and the caller has nothing to clean up.
            self._assert_kb_preconditions(owner_user, name)
        else:
            logger.info("knowledge feature unavailable; creating project %r without a KB", name)

        project: ProjectRow | None = None
        kb_id: str | None = None
        try:
            project = self._projects.create(  # ①
                owner_user_id=owner_user.id,
                name=name,
                goal=goal,
                status=status or "draft",
                start_at=start_at,
                due_at=due_at,
            )
            self._members.add(  # ②
                project_id=project.id,
                subject_type=MEMBER_SUBJECT_USER,
                subject_id=str(owner_user.id),
                user_id=owner_user.id,
                role="owner",
            )
            if bind_kb:
                kb_id = str(  # ③
                    self._knowledge.create_base(owner_user_id=owner_user.id, name=name).id
                )
                self._projects.set_kb_id(project.id, kb_id)  # ④
        except Exception as exc:
            self._compensate_create(project=project, kb_id=kb_id)
            if isinstance(exc, OctopError) and exc.code is ErrorCode.PROJECT_KB_BIND_FAILED:
                raise
            raise OctopError(
                ErrorCode.PROJECT_KB_BIND_FAILED,
                "Could not create the project's knowledge base; the project was not created.",
                details={"cause": type(exc).__name__},
            ) from exc

        created = self._projects.get(project.id)
        if created is None:
            raise OctopError(
                ErrorCode.PROJECT_KB_BIND_FAILED,
                "Project disappeared right after creation.",
            )
        return created

    def _knowledge_usable(self) -> bool:
        """Whether a knowledge base can actually be created right now.

        False on a fresh install (the feature is off until an embedding model is
        configured), which is why project creation must not depend on it.
        """
        capability = get_capability(
            self._services.settings_repo.get,
            getattr(self._services, "provider_repo", None),
        )
        return bool(capability.get("usable"))

    def _assert_kb_preconditions(self, owner_user: ProjectActor, name: str) -> None:
        """Reject before any write when the KB half of creation cannot succeed."""
        # Creating a project creates a knowledge base, so the caller needs the
        # knowledge-base feature too — otherwise step ③ fails after ①② wrote rows.
        if not user_has_permission(owner_user, "knowledge_bases"):
            raise _forbidden("You need knowledge-base access to create a project.")
        owned = self._services.knowledge_repo.count_bases_for_owner(owner_user.id)
        if owned >= MAX_BASES_PER_OWNER:
            raise OctopError(
                ErrorCode.KNOWLEDGE_BASE_LIMIT,
                f"You can create at most {MAX_BASES_PER_OWNER} knowledge bases.",
                details={"max_bases": MAX_BASES_PER_OWNER},
            )
        existing = {base.name for base in self._services.knowledge_repo.list_visible(owner_user.id)}
        if name in existing:
            raise OctopError(
                ErrorCode.KNOWLEDGE_NAME_TAKEN,
                "You already have a knowledge base with this name.",
                details={"name": name},
            )

    def _compensate_create(self, *, project: ProjectRow | None, kb_id: str | None) -> None:
        """Undo whatever a failed create already wrote, newest side effect first.

        Compensating steps must never mask the original error, so failures here
        are logged and swallowed — a stale row is recoverable, a confusing
        exception chain is not.
        """
        if project is None:
            return
        logger.warning(
            "project create failed; compensating (project_id=%s kb_id=%s)", project.id, kb_id
        )
        if kb_id is not None:
            try:
                self._knowledge.delete_base(kb_id, actor_user_id=project.owner_user_id)
            except Exception:  # noqa: BLE001 - compensation must not raise
                logger.exception("compensating KB delete failed (kb_id=%s)", kb_id)
        try:
            # Membership rows cascade with the project.
            self._projects.delete(project.id)
        except Exception:  # noqa: BLE001 - compensation must not raise
            logger.exception("compensating project delete failed (project_id=%s)", project.id)

    # ── update / delete ──────────────────────────────────────────────────────

    def update_project(
        self,
        project_id: str,
        *,
        user: ProjectActor,
        kb_id: object = UNSET,
        **fields: Any,
    ) -> ProjectRow:
        """Patch a project.

        ``kb_id`` is the one field with a higher permission level (PLAN.md §4.3):
        **presence of the key** raises the *whole request* to
        ``PROJECT_MANAGE_CONFIG``, so a write-only actor cannot smuggle other
        edits alongside a rebind. Omitting it leaves the stored value untouched.

        A rebind goes through :meth:`ProjectRepo.set_kb_id` (the only writer);
        ``ProjectRepo.update`` deliberately refuses the column. The previous base
        is kept, never deleted (G2).
        """
        required = PROJECT_MANAGE_CONFIG if kb_id is not UNSET else PROJECT_WRITE
        self.assert_project_role(project_id, user=user, required=required)
        updated = self._projects.update(project_id, **fields) if fields else None
        if updated is None:
            current = self._projects.get(project_id)
            if current is None:
                raise OctopError(ErrorCode.PROJECT_NOT_FOUND, "Project not found.")
            updated = current
        if kb_id is not UNSET:
            target = kb_id if isinstance(kb_id, str) and kb_id else None
            if target is not None:
                self._assert_kb_writable(target, user=user)
            self._projects.set_kb_id(project_id, target)
            refreshed = self._projects.get(project_id)
            if refreshed is None:  # pragma: no cover - the row exists, it was just read
                raise OctopError(ErrorCode.PROJECT_NOT_FOUND, "Project not found.")
            updated = refreshed
        return updated

    def _assert_kb_writable(self, kb_id: str, *, user: ProjectActor) -> None:
        """Map the KB primitives onto the two refusal codes frozen in PLAN.md §4.2.

        ``LookupError`` = the base does not exist / is not visible to this user →
        the existing ``KNOWLEDGE_NOT_FOUND``; ``PermissionError`` = visible but not
        writable → the new ``PROJECT_KB_FORBIDDEN``. Neither may escape as a 500.
        """
        try:
            self._knowledge.get_writable_base(
                kb_id,
                actor_user_id=user.id,
                is_admin=bool(getattr(user, "is_admin", False)),
            )
        except LookupError as exc:
            raise OctopError(ErrorCode.KNOWLEDGE_NOT_FOUND, "Knowledge base not found.") from exc
        except PermissionError as exc:
            raise OctopError(
                ErrorCode.PROJECT_KB_FORBIDDEN,
                f"no write access to knowledge base {kb_id!r}",
            ) from exc

    def transition_project(self, project_id: str, *, user: ProjectActor, target: str) -> ProjectRow:
        """Move a project along the state machine (plan T2.1 ②).

        Archiving is owner-only; every other transition needs ``write``.
        """
        if target not in PROJECT_STATUSES:
            raise _project_status_invalid(f"Unknown project status: '{target}'.")
        project = self._require_project(project_id)
        required = PROJECT_ARCHIVE if target == "archived" else PROJECT_WRITE
        self.assert_project_role(project_id, user=user, required=required)
        self._assert_transition(project, target)
        updated = self._projects.update(project_id, status=target)
        if updated is None:
            raise OctopError(ErrorCode.PROJECT_NOT_FOUND, "Project not found.")
        return updated

    def delete_project(self, project_id: str, *, user: ProjectActor) -> bool:
        """Delete a project and its child rows (owner only).

        The project's knowledge base is deliberately **not** deleted: it may hold
        documents, and destroying them as a side effect of deleting a project is
        not something the caller asked for. It stays in the owner's KB list.
        """
        self.assert_project_role(project_id, user=user, required=PROJECT_ARCHIVE)
        return self._projects.delete(project_id)

    def _assert_transition(self, project: ProjectRow, target: str) -> None:
        if target not in _TRANSITIONS.get(project.status, frozenset()):
            raise _project_status_invalid(
                f"Cannot change project status from '{project.status}' to '{target}'."
            )
        if target == "active":
            self._assert_activation_ready(project)

    def _assert_activation_ready(self, project: ProjectRow) -> None:
        """``draft -> active`` needs at least one member and a sitting owner."""
        if self._members.count(project.id) < 1:
            raise _project_status_invalid("Add at least one member before activating.")
        owner_role = self._members.role_of(
            project.id, MEMBER_SUBJECT_USER, str(project.owner_user_id)
        )
        if owner_role != "owner":
            raise _project_status_invalid("The project owner must be a member with the owner role.")

    # ── membership ───────────────────────────────────────────────────────────

    def add_member(
        self,
        project_id: str,
        *,
        user: ProjectActor,
        subject_type: str,
        subject_id: str,
        role: str = "member",
        subject_user_id: int | None = None,
    ) -> ProjectMemberRow:
        self.assert_project_role(project_id, user=user, required=PROJECT_MANAGE_MEMBERS)
        if role not in PROJECT_ROLES:
            raise _member_invalid(f"Unknown project role: '{role}'.")
        project = self._require_project(project_id)
        self._assert_owner_role_untouched(project, subject_type, subject_id, role)
        return self._members.add(
            project_id=project_id,
            subject_type=subject_type,
            subject_id=subject_id,
            user_id=subject_user_id,
            role=role,
        )

    def remove_member(
        self,
        project_id: str,
        *,
        user: ProjectActor,
        subject_type: str,
        subject_id: str,
    ) -> bool:
        self.assert_project_role(project_id, user=user, required=PROJECT_MANAGE_MEMBERS)
        project = self._require_project(project_id)
        if subject_type == MEMBER_SUBJECT_USER and str(project.owner_user_id) == subject_id:
            raise _member_invalid("The project owner cannot be removed.")
        return self._members.remove(project_id, subject_type, subject_id)

    def _assert_owner_role_untouched(
        self, project: ProjectRow, subject_type: str, subject_id: str, role: str
    ) -> None:
        """Re-adding the owner with any role but ``owner`` would break activation."""
        if subject_type != MEMBER_SUBJECT_USER:
            return
        if str(project.owner_user_id) == subject_id and role != "owner":
            raise _member_invalid("The project owner must keep the owner role.")

    # ── tasks (T2.3) ─────────────────────────────────────────────────────────

    def list_tasks(
        self, project_id: str, *, user: ProjectActor, status: str | None = None
    ) -> list[ProjectTaskRow]:
        self.assert_project_role(project_id, user=user, required=PROJECT_READ)
        return self._tasks.list_by_project(project_id, status=status)

    def get_task(self, project_id: str, task_id: str, *, user: ProjectActor) -> ProjectTaskRow:
        task = self._require_task(project_id, task_id)
        self.assert_project_role(project_id, user=user, required=PROJECT_READ)
        return task

    def create_task(
        self,
        project_id: str,
        *,
        user: ProjectActor,
        title: str,
        tags: Sequence[object] | None = None,
        custom_fields: Mapping[str, object] | None = None,
        attachment_ids: Sequence[object] | None = None,
        **fields: Any,
    ) -> ProjectTaskRow:
        """Create a task; ``status=None`` lands in ``planning``.

        Any status in ``TASK_STATUSES`` is a legal *initial* status (the board lets
        a card be created straight into its column, PLAN.md §2.1). This does not
        bypass the state machine: every later move still goes through
        :meth:`transition_task`, which enforces the adjacency graph.

        The optional metadata is written by the **four-step orchestration** frozen
        in PLAN.md §2.3 — task row, tags, custom-field values, then staged
        attachments. Any failure in steps ②-④ rolls back in **reverse order** and
        finally compensating-deletes the task row, so a refused request never
        leaves a half-built task behind. Files are never deleted by compensation.
        """
        self.assert_project_role(project_id, user=user, required=PROJECT_WRITE)
        title = title.strip()
        if not title:
            raise ValueError("task title is required")
        status = fields.pop("status", None) or "planning"
        if status not in TASK_STATUSES:
            raise _task_status_invalid(f"Unknown task status: '{status}'.")
        _check_task_dates(fields.get("start_at"), fields.get("due_at"))
        task = self._tasks.create(  # ①
            project_id=project_id,
            title=title,
            created_by=user.id,
            status=status,
            **fields,
        )
        self._record(
            project_id,
            task.id,
            user,
            TIMELINE_TASK_CREATED,
            {"title": task.title},
        )
        try:
            self._apply_task_metadata(
                project_id,
                task.id,
                user=user,
                tags=tags,
                custom_fields=custom_fields,
                attachment_ids=attachment_ids,
            )
        except Exception:
            self._compensate_task_create(
                project_id, task.id, user=user, attachment_ids=attachment_ids
            )
            raise
        return task

    def _apply_task_metadata(
        self,
        project_id: str,
        task_id: str,
        *,
        user: ProjectActor,
        tags: Sequence[object] | None,
        custom_fields: Mapping[str, object] | None,
        attachment_ids: Sequence[object] | None,
    ) -> None:
        """Steps ②-④ of PLAN.md §2.3, in order, on the task that already exists."""
        tag_ids = [str(tag) for tag in (tags or [])]
        if tag_ids:
            self.set_task_tags(project_id, task_id, user=user, tag_ids=tag_ids)  # ②
        if custom_fields is not None:
            self.set_task_values(project_id, task_id, user=user, values=custom_fields)  # ③
        pending = [str(aid) for aid in (attachment_ids or [])]
        if pending:
            self._attachment_service().bind_pending(  # ④
                project_id, task_id, pending, user=user
            )

    def set_task_tags(
        self, project_id: str, task_id: str, *, user: ProjectActor, tag_ids: Sequence[object]
    ) -> Any:
        """Replace a task's tag set (PLAN.md §4); shared by create and PATCH."""
        return self._tag_service().set_task_tags(project_id, task_id, user=user, tag_ids=tag_ids)

    def set_task_values(
        self,
        project_id: str,
        task_id: str,
        *,
        user: ProjectActor,
        values: Mapping[str, object],
    ) -> Any:
        """Replace a task's custom-field values (PLAN.md §6); create and PATCH."""
        return self._custom_field_service().set_task_values(
            project_id, task_id, user=user, values=values
        )

    def _compensate_task_create(
        self,
        project_id: str,
        task_id: str,
        *,
        user: ProjectActor,
        attachment_ids: Sequence[object] | None,
    ) -> None:
        """Reverse-order rollback for a failed create (PLAN.md §2.3).

        Attachments go back to *pending* first (``task_id`` set to NULL — rows and
        files are untouched, the user may retry), then the task row is deleted,
        which takes the tag links and field values with it via their cascades.
        Both halves are idempotent: unbinding an unbound row is a no-op and
        ``delete_task`` returns ``False`` for an already-deleted task.
        """
        pending = [str(aid) for aid in (attachment_ids or [])]
        if pending:
            self._attachment_service().unbind_all(task_id, pending)
        self.delete_task(project_id, task_id, user=user)

    def _tag_service(self) -> Any:
        from octop.infra.projects.tags import ProjectTagService  # noqa: PLC0415 - cycle-safe

        return ProjectTagService(self._services, project_service=self)

    def _custom_field_service(self) -> Any:
        from octop.infra.projects.custom_fields import (  # noqa: PLC0415 - cycle-safe
            ProjectCustomFieldService,
        )

        return ProjectCustomFieldService(self._services, project_service=self)

    def _attachment_service(self) -> Any:
        from octop.infra.projects.attachments import (  # noqa: PLC0415 - cycle-safe
            ProjectAttachmentService,
        )

        return ProjectAttachmentService(self._services, project_service=self)

    def update_task(
        self, project_id: str, task_id: str, *, user: ProjectActor, **fields: Any
    ) -> ProjectTaskRow:
        """Patch task fields other than status (that goes through the state machine)."""
        task = self._require_task(project_id, task_id)
        self.assert_project_role(project_id, user=user, required=PROJECT_WRITE)
        if fields.get("status") is not None:
            raise _task_status_invalid("use transition_task() to change status")
        fields.pop("status", None)
        if not fields:
            return task
        if "start_at" in fields or "due_at" in fields:
            _check_task_dates(
                fields.get("start_at", task.start_at),
                fields.get("due_at", task.due_at),
            )
        updated = self._tasks.update(task_id, **fields)
        if updated is None:
            raise OctopError(ErrorCode.PROJECT_TASK_NOT_FOUND, "Task not found.")
        self._record(
            task.project_id,
            task_id,
            user,
            TIMELINE_TASK_UPDATED,
            {"fields": sorted(fields)},
        )
        if "assignee_id" in fields or "assignee_type" in fields:
            self._record(
                task.project_id,
                task_id,
                user,
                TIMELINE_TASK_ASSIGNED,
                {"assignee_type": updated.assignee_type, "assignee_id": updated.assignee_id},
            )
        return updated

    def transition_task(
        self, project_id: str, task_id: str, *, user: ProjectActor, target: str
    ) -> ProjectTaskRow:
        """Move a task along the task state machine."""
        if target not in TASK_STATUSES:
            raise _task_status_invalid(f"Unknown task status: '{target}'.")
        task = self._require_task(project_id, task_id)
        self.assert_project_role(project_id, user=user, required=PROJECT_WRITE)
        if target not in _TASK_TRANSITIONS.get(task.status, frozenset()):
            raise _task_status_invalid(
                f"Cannot change task status from '{task.status}' to '{target}'."
            )
        updated = self._tasks.update(task_id, status=target)
        if updated is None:
            raise OctopError(ErrorCode.PROJECT_TASK_NOT_FOUND, "Task not found.")
        self._record(
            task.project_id,
            task_id,
            user,
            TIMELINE_TASK_STATUS_CHANGED,
            {"from": task.status, "to": target},
        )
        return updated

    def delete_task(self, project_id: str, task_id: str, *, user: ProjectActor) -> bool:
        task = self._require_task(project_id, task_id)
        self.assert_project_role(project_id, user=user, required=PROJECT_WRITE)
        deleted = self._tasks.delete(task_id)
        if deleted:
            # Keep the task id on the event: timeline_events.task_id has no FK
            # precisely so history survives the row it describes.
            self._record(
                task.project_id,
                task_id,
                user,
                TIMELINE_TASK_DELETED,
                {"title": task.title},
            )
        return deleted

    # ── dispatch (T2.5) ──────────────────────────────────────────────────────

    async def dispatch_task(
        self, project_id: str, task_id: str, *, user: ProjectActor
    ) -> ProjectTaskRow:
        """Dispatch a task to its agent/team assignee (plan T2.5 ①-⑥).

        Steps ①-④ — fresh thread, task prompt, one agent turn under the target
        session's serialization lock — run in
        :func:`octop.infra.projects.dispatch.run_dispatch_turn`. The task write
        (⑤) and the timeline row (⑥) stay here with the other task mutations.

        A task with no dispatchable assignee is a caller error, so an
        ``assignee_type`` outside ``agent``/``team`` (or an empty assignee id)
        raises ``PROJECT_TASK_DISPATCH_INVALID`` (409) instead of escaping as an
        unhandled ``ValueError``. A missing or stopped assignee keeps the
        registry's own ``AGENT_NOT_FOUND`` / ``AGENT_NOT_RUNNING``.

        Nothing is written when the turn fails: the thread stays unbound and the
        caller sees the failure rather than a task that claims to be dispatched.
        """
        task = self._require_task(project_id, task_id)
        self.assert_project_role(project_id, user=user, required=PROJECT_WRITE)
        project = self._require_project(project_id)
        if self._agent_manager is None or self._gateway is None:
            # No booted runtime means no agent can be running right now.
            raise OctopError(ErrorCode.AGENT_NOT_RUNNING, "The agent runtime is not available.")
        thread_id = await run_dispatch_turn(
            repos=self._services.repos,
            agent_manager=self._agent_manager,
            gateway=self._gateway,
            project=project,
            task=task,
            dispatcher_user_id=user.id,
        )
        updated = self._tasks.update(task_id, thread_id=thread_id)
        if updated is None:
            raise OctopError(ErrorCode.PROJECT_TASK_NOT_FOUND, "Task not found.")
        self._record(
            project_id,
            task_id,
            user,
            TIMELINE_TASK_DISPATCHED,
            {
                "assignee_type": updated.assignee_type,
                "assignee_id": updated.assignee_id,
                "thread_id": thread_id,
            },
        )
        return updated

    def list_timeline(
        self, project_id: str, *, user: ProjectActor, limit: int | None = None
    ) -> list[TimelineEventRow]:
        """Chronological project timeline (oldest first)."""
        self.assert_project_role(project_id, user=user, required=PROJECT_READ)
        return self._timeline.list_by_project(project_id, limit=limit)

    def _record(
        self,
        project_id: str,
        task_id: str | None,
        user: ProjectActor,
        action: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Append a timeline row.

        Deliberately not wrapped in a try/except: the task write has already
        committed by now, and a silently missing audit row would make the
        timeline quietly incomplete (M16 / AC-12).
        """
        self._timeline.append(
            project_id=project_id,
            task_id=task_id,
            actor=actor_ref("user", user.id),
            action=action,
            payload=payload,
        )

    # ── internals ────────────────────────────────────────────────────────────

    def _require_task(self, project_id: str, task_id: str) -> ProjectTaskRow:
        """Load a task **through its project path**.

        Both a missing task and a task that lives in another project are
        ``PROJECT_TASK_NOT_FOUND``: the ``{project_id}`` segment is part of the
        resource's identity, so a mismatched pair must never reach the task. Every
        task route takes both ids — resolving the task's own project instead would
        let ``/projects/B/tasks/<task-of-A>`` edit A through B's URL, which becomes
        an escalation for any caller that trusts the path's project.
        """
        task = self._tasks.get(task_id)
        if task is None or task.project_id != project_id:
            raise OctopError(ErrorCode.PROJECT_TASK_NOT_FOUND, "Task not found.")
        return task

    def _require_project(self, project_id: str) -> ProjectRow:
        project = self._projects.get(project_id)
        if project is None:
            raise OctopError(ErrorCode.PROJECT_NOT_FOUND, "Project not found.")
        return project

    def _role_of(self, project: ProjectRow, user: ProjectActor) -> str | None:
        if project.owner_user_id == user.id:
            return "owner"
        return self._members.role_of(project.id, MEMBER_SUBJECT_USER, str(user.id))

    def _assert_feature_enabled(self, user: ProjectActor) -> None:
        if not user_has_permission(user, "projects"):
            raise _forbidden("You do not have access to the projects module.")
