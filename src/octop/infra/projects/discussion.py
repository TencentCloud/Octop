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
