"""Project discussion line — plan T3.1 (the first half of the 双层模型).

The plan splits a project's collaboration record in two layers:

* the **discussion line** — free-form ``project_comments``, on a project or on one
  of its tasks (this module), and
* the **requirement layer** — typed ``requirement_nodes`` distilled out of it
  (T3.2, not implemented here).

A comment is written either by a person (dashboard) or by an agent during a task
turn, which is what ``author_type`` and ``source`` record. ``task_id`` is the
soft link onto a task's line: it carries no database foreign key, so the repo
checks it at write time and a comment can never attach to another project's task.

Permission logic is deliberately **not** re-implemented here. :class:`ProjectService`
owns the §4.6 matrix, so every entry point delegates to its
:meth:`~octop.infra.projects.service.ProjectService.assert_project_role`.
"""

from __future__ import annotations

import json

from octop.infra.db.repos.audit import AuditRepo
from octop.infra.db.repos.project_content import (
    COMMENT_AUTHOR_AGENT,
    COMMENT_AUTHOR_TYPES,
    COMMENT_AUTHOR_USER,
    COMMENT_NODE_CONCLUSION,
    COMMENT_NODE_NONE,
    COMMENT_SOURCE_AGENT,
    COMMENT_SOURCE_DASHBOARD,
    ProjectCommentRow,
)
from octop.infra.db.services import SharedServices
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.projects.service import (
    PROJECT_READ,
    PROJECT_WRITE,
    ProjectActor,
    ProjectService,
)

#: How much of a replaced comment body the audit payload keeps (P4b: truncate **and** flag).
_AUDIT_BODY_LIMIT = 500


def _require_body(body: str) -> str:
    """A blank comment is a caller error, not an empty row.

    The body is otherwise stored verbatim: it is free-form markdown, where
    leading indentation is significant inside code blocks.
    """
    if not body.strip():
        raise ValueError("comment body is required")
    return body


class ProjectDiscussion:
    """Reads and writes a project's discussion line (``project_comments``)."""

    def __init__(self, services: SharedServices) -> None:
        self._comments = services.project_comment_repo
        self._projects = ProjectService(services)
        self._services = services
        # audit_log is the **history**; the conclusion columns on the comment row
        # are the **only** authority for the current state (PLAN.md §2.1c). No code
        # may derive the current conclusion by reading ``audit_log``.
        self._audit = getattr(services, "audit_repo", None) or AuditRepo(services.db)
        self._artifacts = getattr(services, "project_artifact_repo", None)

    # ── reads ────────────────────────────────────────────────────────────────

    def list_comments(
        self,
        project_id: str,
        *,
        user: ProjectActor,
        task_id: str | None = None,
        concluded: bool | None = None,
    ) -> list[ProjectCommentRow]:
        """A project's comments, oldest first; ``task_id`` narrows to one task's line
        and ``concluded`` to (or away from) the adopted conclusion."""
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_READ)
        return self._comments.list_by_project(project_id, task_id=task_id, concluded=concluded)

    def _require_own_comment(
        self, project_id: str, comment_id: str, *, user: ProjectActor
    ) -> ProjectCommentRow:
        """The comment must exist in this project **and** be authored by ``user``.

        The author check matches ``author_type`` *and* ``author_id``: an agent row
        whose id happens to equal a user's id is not that user's comment
        (``019_projects.sql`` stores the two columns separately).
        """
        row = self._comments.get(comment_id)
        if row is None or row.project_id != project_id:
            raise OctopError(ErrorCode.PROJECT_NOT_FOUND, "Comment not found in this project.")
        if row.author_type != COMMENT_AUTHOR_USER or row.author_id != str(user.id):
            raise OctopError(
                ErrorCode.PROJECT_FORBIDDEN,
                "This comment belongs to another author.",
            )
        return row

    def _may_govern(self, project_id: str, user: ProjectActor) -> bool:
        """The governance line (SPEC P1), parallel to — not inside — the role check.

        ``assert_project_role`` governs *project roles* and deliberately gives
        ``is_admin`` no bypass. This gate governs the **governance surface**:
        a platform admin acts without being a project member, and a project owner
        is recognised straight from ``projects.owner_user_id`` (which is exactly
        what ``_role_of`` does — the owner need not hold a member row).

        Kept as its own function on purpose: an ``allow_governance=True`` default on
        the author helper would fork the meaning of a call depending on an argument
        someone can forget to pass.
        """
        if bool(getattr(user, "is_admin", False)):
            return True
        row = self._services.project_repo.get(project_id)
        return row is not None and row.owner_user_id == user.id

    def _require_comment_in_project(self, project_id: str, comment_id: str) -> ProjectCommentRow:
        """404-only lookup used on the governance path (no author assertion)."""
        row = self._comments.get(comment_id)
        if row is None or row.project_id != project_id:
            raise OctopError(ErrorCode.PROJECT_NOT_FOUND, "Comment not found in this project.")
        return row

    def _require_author_or_governance(
        self, project_id: str, comment_id: str, *, user: ProjectActor
    ) -> ProjectCommentRow:
        """Author **or** governance, explicitly composed at the call site."""
        if self._may_govern(project_id, user):
            return self._require_comment_in_project(project_id, comment_id)
        return self._require_own_comment(project_id, comment_id, user=user)

    def delete_comment(self, project_id: str, comment_id: str, *, user: ProjectActor) -> bool:
        """Delete one's own comment, its attachments and an audit row — atomically.

        ★ Not writing the conclusion branch below means the default behaviour is
        (c): the conclusion would keep pointing at a deleted comment, i.e. the
        project's current conclusion silently dangles. The refusal (option a) makes
        the caller un-adopt first, so the state stays consistent.
        """
        # Governance short-circuit (SPEC P1): an admin acts without being a member,
        # so the project-role check is skipped on that line — otherwise a
        # non-member admin would be refused by ``assert_project_role`` before the
        # governance gate could ever allow it. Everyone else still runs the normal
        # role check, which keeps ``is_admin`` from bypassing anything else.
        if not self._may_govern(project_id, user):
            self._projects.assert_project_role(project_id, user=user, required=PROJECT_WRITE)
        row = self._require_author_or_governance(project_id, comment_id, user=user)
        if row.node_type == COMMENT_NODE_CONCLUSION:
            raise OctopError(
                ErrorCode.PROJECT_COMMENT_CONCLUDED,
                "This comment is the adopted conclusion; un-adopt it before deleting.",
            )
        payload = json.dumps(
            {"project_id": project_id, "task_id": row.task_id, "node_type": row.node_type},
            ensure_ascii=False,
        )
        with self._services.db.transaction() as conn:
            if self._artifacts is not None:
                # Attachments die with their comment: no orphan artifact rows.
                self._artifacts.delete_by_comment(comment_id, conn=conn)
            removed = self._comments.delete(comment_id, conn=conn)
            self._audit.write(
                actor=getattr(user, "username", None) or str(user.id),
                action="project.comment.delete",
                target=comment_id,
                payload=payload,
                conn=conn,
            )
        return bool(removed)

    def edit_comment(
        self, project_id: str, comment_id: str, *, user: ProjectActor, body: str
    ) -> ProjectCommentRow:
        """Replace a comment's text; the previous text goes to ``audit_log``.

        Long bodies are truncated **and flagged** in the payload (``P4b``), so a
        reader can tell "this is the whole old text" from "this is a prefix".
        """
        # Governance short-circuit (SPEC P1): an admin acts without being a member,
        # so the project-role check is skipped on that line — otherwise a
        # non-member admin would be refused by ``assert_project_role`` before the
        # governance gate could ever allow it. Everyone else still runs the normal
        # role check, which keeps ``is_admin`` from bypassing anything else.
        if not self._may_govern(project_id, user):
            self._projects.assert_project_role(project_id, user=user, required=PROJECT_WRITE)
        row = self._require_author_or_governance(project_id, comment_id, user=user)
        previous = row.body
        limit = _AUDIT_BODY_LIMIT
        truncated = len(previous) > limit
        payload = json.dumps(
            {
                "project_id": project_id,
                "task_id": row.task_id,
                "old_body": previous[:limit],
                "old_body_truncated": truncated,
                "old_body_length": len(previous),
            },
            ensure_ascii=False,
        )
        with self._services.db.transaction() as conn:
            self._comments.update_body(comment_id, _require_body(body), conn=conn)
            self._audit.write(
                actor=getattr(user, "username", None) or str(user.id),
                action="project.comment.edit",
                target=comment_id,
                payload=payload,
                conn=conn,
            )
        refreshed = self._comments.get(comment_id)
        if refreshed is None:  # pragma: no cover - the row was just updated
            raise OctopError(ErrorCode.PROJECT_NOT_FOUND, "Comment not found in this project.")
        return refreshed

    def set_conclusion(
        self,
        project_id: str,
        comment_id: str,
        *,
        user: ProjectActor,
        concluded: bool,
    ) -> ProjectCommentRow:
        """Adopt (or un-adopt) one comment as the discussion's conclusion.

        Same existing ``write`` check as every other comment write, and the same
        ``project_comments`` row — the only new thing is the ``node_type`` value.
        A comment id that does not live in this project is a 404, mirroring the
        other "id not in this project" surfaces.
        """
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_WRITE)
        row = self._comments.get(comment_id)
        if row is None or row.project_id != project_id:
            raise OctopError(ErrorCode.PROJECT_NOT_FOUND, "Comment not found in this project.")
        node_type = COMMENT_NODE_CONCLUSION if concluded else COMMENT_NODE_NONE
        # Audit records the **identifier**, never the display name (a later rename
        # must not rewrite history). Adopting stores the actor, un-adopting clears
        # both columns in the same UPDATE, so `NULL/NULL <=> not the conclusion`.
        actor_type = "user"
        actor_id = str(user.id)
        by_type = actor_type if concluded else None
        by_id = actor_id if concluded else None
        action = "project.comment.conclude" if concluded else "project.comment.unconclude"
        payload = json.dumps(
            {
                "project_id": project_id,
                "task_id": row.task_id,
                "node_type": node_type,
                "concluded_by_type": by_type,
                "concluded_by_id": by_id,
            },
            ensure_ascii=False,
        )
        # One transaction for state **and** audit: a failed audit write must roll the
        # state back — never "columns changed, log missing" (PLAN.md §2.1c P6).
        with self._services.db.transaction() as conn:
            self._comments.set_node_type(
                comment_id,
                node_type,
                concluded_by_type=by_type,
                concluded_by_id=by_id,
                conn=conn,
            )
            self._audit.write(
                actor=getattr(user, "username", None) or str(user.id),
                action=action,
                target=comment_id,
                payload=payload,
                conn=conn,
            )
        refreshed = self._comments.get(comment_id)
        if refreshed is None:  # pragma: no cover - the row was just updated
            raise OctopError(ErrorCode.PROJECT_NOT_FOUND, "Comment not found in this project.")
        return refreshed

    def count_for_task(self, project_id: str, task_id: str) -> int:
        """How many comments one task's discussion line holds (task board badge)."""
        return self._comments.count_by_project(project_id, task_id=task_id)

    # ── writes ───────────────────────────────────────────────────────────────

    def add_comment(
        self,
        project_id: str,
        *,
        user: ProjectActor,
        body: str,
        task_id: str | None = None,
        thread_id: str | None = None,
        source: str = COMMENT_SOURCE_DASHBOARD,
        author_type: str = COMMENT_AUTHOR_USER,
        author_id: str | None = None,
    ) -> ProjectCommentRow:
        """Add one comment to a project or task line; requires ``write`` (§4.6).

        ``author_id`` defaults to the acting user, which is the dashboard path;
        an ``agent`` author names the agent explicitly, because a user id recorded
        as an agent id would misattribute the words (see :meth:`add_agent_comment`).
        """
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_WRITE)
        if author_type not in COMMENT_AUTHOR_TYPES:
            raise ValueError(f"unknown comment author_type: {author_type}")
        if author_id is None:
            if author_type != COMMENT_AUTHOR_USER:
                raise ValueError("an agent comment must name its author_id")
            author_id = str(user.id)
        return self._comments.create(
            project_id=project_id,
            task_id=task_id,
            thread_id=thread_id,
            author_type=author_type,
            author_id=author_id,
            body=_require_body(body),
            source=source,
        )

    def add_agent_comment(
        self,
        project_id: str,
        *,
        user: ProjectActor,
        agent_id: str,
        body: str,
        task_id: str | None = None,
        thread_id: str | None = None,
    ) -> ProjectCommentRow:
        """Record an agent's output on a task's discussion line (T3.2 / T5 write this).

        ``user`` is the member whose turn produced the output, so the permission
        check stays an ordinary ``write`` check, while ``author_type='agent'`` and
        ``source='agent'`` record who actually wrote the words.
        """
        return self.add_comment(
            project_id,
            user=user,
            body=body,
            task_id=task_id,
            thread_id=thread_id,
            source=COMMENT_SOURCE_AGENT,
            author_type=COMMENT_AUTHOR_AGENT,
            author_id=str(agent_id),
        )
