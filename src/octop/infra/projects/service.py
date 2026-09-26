"""Project domain service — lifecycle, knowledge-base binding, permissions.

Three responsibilities beyond the repos (plan T2.1):

1. **Knowledge-base lifecycle.** A project owns one KB whose name mirrors the
   project name. Creation is a multi-step, cross-repo flow, and the repos each
   open their own transaction — there is no shared transaction to roll back.
   Every failure therefore runs an explicit **compensating delete** so we never
   leave a project without its KB, or a KB without its project.
2. **State machine.** ``draft -> active -> (paused|archived)``; ``archived`` is
   terminal and makes the project read-only.
3. **Permission matrix** (plan §4.6) behind :meth:`ProjectService.assert_project_role`.

Membership is the only way in: a platform admin who is not a project member is
rejected like anyone else. The coarse ``projects`` permission key gates "may use
the project feature"; the ``project_members`` join gates the data.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from octop.infra.db.repos.projects import (
    MEMBER_SUBJECT_USER,
    PROJECT_ROLES,
    ProjectMemberRow,
    ProjectRow,
)
from octop.infra.db.services import SharedServices
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.knowledge.service import MAX_BASES_PER_OWNER, KnowledgeService
from octop.infra.users.permissions import user_has_permission

logger = logging.getLogger(__name__)

# ── permission levels (§4.6), weakest first ──────────────────────────────────
PROJECT_READ = "read"
PROJECT_WRITE = "write"
PROJECT_CONFIRM = "confirm"
PROJECT_MANAGE_MEMBERS = "manage_members"
PROJECT_ARCHIVE = "archive"

PROJECT_ACTIONS: tuple[str, ...] = (
    PROJECT_READ,
    PROJECT_WRITE,
    PROJECT_CONFIRM,
    PROJECT_MANAGE_MEMBERS,
    PROJECT_ARCHIVE,
)

#: Which levels each role satisfies. Note ``admin`` deliberately lacks
#: ``archive`` — §4.6 gives archive/delete to the owner alone.
_ROLE_LEVELS: dict[str, frozenset[str]] = {
    "owner": frozenset(PROJECT_ACTIONS),
    "admin": frozenset({PROJECT_READ, PROJECT_WRITE, PROJECT_CONFIRM, PROJECT_MANAGE_MEMBERS}),
    "member": frozenset({PROJECT_READ, PROJECT_WRITE}),
    "viewer": frozenset({PROJECT_READ}),
}

#: Allowed status transitions. ``archived`` is terminal.
_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"active"}),
    "active": frozenset({"paused", "archived"}),
    "paused": frozenset({"active", "archived"}),
    "archived": frozenset(),
}


class ProjectActor(Protocol):
    """The slice of a user row this service needs."""

    id: int

    @property
    def is_admin(self) -> bool: ...

    permissions: list[str]


def _forbidden(message: str) -> OctopError:
    return OctopError(ErrorCode.FORBIDDEN, message)


def _invalid_transition(message: str) -> OctopError:
    return OctopError(ErrorCode.PROJECT_INVALID_TRANSITION, message)


class ProjectService:
    def __init__(self, services: SharedServices) -> None:
        self._services = services
        self._projects = services.project_repo
        self._members = services.project_member_repo
        self._tasks = services.project_task_repo
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
            raise _forbidden(f"Your role in this project ({role}) cannot perform '{required}'.")
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
        start_at: int | None = None,
        due_at: int | None = None,
    ) -> ProjectRow:
        """Create a project together with its knowledge base.

        Steps (each with an explicit failure branch):

        ⓪ preconditions — no side effects, so an unactionable ⓪ leaves nothing behind
        ① ``projects`` row
        ② owner membership row
        ③ knowledge base
        ④ write ``kb_id`` back onto the project

        A failure in ③ or ④ deletes whatever the earlier steps created, then
        raises ``PROJECT_KB_BIND_FAILED``.
        """
        self._assert_feature_enabled(owner_user)
        name = name.strip()
        if not name:
            raise ValueError("project name is required")

        # ⓪ No side effects yet, so these surface the KB error codes directly —
        #    they are actionable and the caller has nothing to clean up.
        self._assert_kb_preconditions(owner_user, name)

        project: ProjectRow | None = None
        kb_id: str | None = None
        try:
            project = self._projects.create(  # ①
                owner_user_id=owner_user.id,
                name=name,
                goal=goal,
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
            kb_id = str(self._knowledge.create_base(owner_user_id=owner_user.id, name=name).id)  # ③
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
        **fields: Any,
    ) -> ProjectRow:
        self.assert_project_role(project_id, user=user, required=PROJECT_WRITE)
        updated = self._projects.update(project_id, **fields)
        if updated is None:
            raise OctopError(ErrorCode.NOT_FOUND, "Project not found.")
        return updated

    def transition_project(self, project_id: str, *, user: ProjectActor, target: str) -> ProjectRow:
        """Move a project along the state machine (plan T2.1 ②).

        Archiving is owner-only; every other transition needs ``write``.
        """
        if target not in _TRANSITIONS:
            raise ValueError(f"unknown project status: {target}")
        project = self._require_project(project_id)
        required = PROJECT_ARCHIVE if target == "archived" else PROJECT_WRITE
        self.assert_project_role(project_id, user=user, required=required)
        self._assert_transition(project, target)
        updated = self._projects.update(project_id, status=target)
        if updated is None:
            raise OctopError(ErrorCode.NOT_FOUND, "Project not found.")
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
            raise _invalid_transition(
                f"Cannot change project status from '{project.status}' to '{target}'."
            )
        if target == "active":
            self._assert_activation_ready(project)

    def _assert_activation_ready(self, project: ProjectRow) -> None:
        """``draft -> active`` needs at least one member and a sitting owner."""
        if self._members.count(project.id) < 1:
            raise _invalid_transition("Add at least one member before activating.")
        owner_role = self._members.role_of(
            project.id, MEMBER_SUBJECT_USER, str(project.owner_user_id)
        )
        if owner_role != "owner":
            raise _invalid_transition("The project owner must be a member with the owner role.")

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
            raise ValueError(f"unknown project role: {role}")
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
            raise _invalid_transition("The project owner cannot be removed.")
        return self._members.remove(project_id, subject_type, subject_id)

    def _assert_owner_role_untouched(
        self, project: ProjectRow, subject_type: str, subject_id: str, role: str
    ) -> None:
        """Re-adding the owner with any role but ``owner`` would break activation."""
        if subject_type != MEMBER_SUBJECT_USER:
            return
        if str(project.owner_user_id) == subject_id and role != "owner":
            raise _invalid_transition("The project owner must keep the owner role.")

    # ── internals ────────────────────────────────────────────────────────────

    def _require_project(self, project_id: str) -> ProjectRow:
        project = self._projects.get(project_id)
        if project is None:
            raise OctopError(ErrorCode.NOT_FOUND, "Project not found.")
        return project

    def _role_of(self, project: ProjectRow, user: ProjectActor) -> str | None:
        if project.owner_user_id == user.id:
            return "owner"
        return self._members.role_of(project.id, MEMBER_SUBJECT_USER, str(user.id))

    def _assert_feature_enabled(self, user: ProjectActor) -> None:
        if not user_has_permission(user, "projects"):
            raise _forbidden("You do not have access to the projects module.")
