"""Project tags: validation, permissions, and the write path.

The tag **definition** and its **task links** live in
``repos/project_tags.py``. This module owns everything above SQL (PLAN.md §4):

* every write asserts ``PROJECT_WRITE`` through
  :meth:`ProjectService.assert_project_role` — there is no second permission
  check anywhere in the tag code path;
* ``name`` / ``color`` are validated here and nowhere else;
* a ``tag_id`` is only usable inside the project that owns it, so a tag from
  project A can never be attached to a task of project B.

All rejections use the single frozen code ``PROJECT_TASK_TAG_INVALID`` (409),
whose Chinese message already covers both "does not exist" and "belongs to
another project".
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from octop.infra.db.repos._base import UNSET
from octop.infra.db.repos.project_tags import ProjectTagRepo, ProjectTagRow
from octop.infra.db.services import SharedServices
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.projects.service import PROJECT_READ, PROJECT_WRITE, ProjectActor, ProjectService

#: ``name`` is trimmed, must be non-empty, and may not exceed this length.
TAG_NAME_MAX_LENGTH = 32

#: ``color`` is either empty (no colour) or an opaque ``#RRGGBB``.
TAG_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")


def _tag_invalid(message: str) -> OctopError:
    """The one frozen rejection for every tag-side rule (PLAN.md §2.2)."""
    return OctopError(ErrorCode.PROJECT_TASK_TAG_INVALID, message)


def normalize_tag_name(raw: object) -> str:
    name = str(raw or "").strip()
    if not name:
        raise _tag_invalid("A tag name is required.")
    if len(name) > TAG_NAME_MAX_LENGTH:
        raise _tag_invalid(f"A tag name may not exceed {TAG_NAME_MAX_LENGTH} characters.")
    return name


def normalize_tag_color(raw: object) -> str:
    color = str(raw or "").strip()
    if not color:
        return ""
    if not TAG_COLOR_PATTERN.match(color):
        raise _tag_invalid("A tag colour must be empty or '#RRGGBB'.")
    return color.lower()


class ProjectTagService:
    """Tag definitions and per-task links for one project at a time."""

    def __init__(
        self,
        services: SharedServices,
        *,
        project_service: ProjectService | None = None,
    ) -> None:
        self._services = services
        self._tags: ProjectTagRepo = services.project_tag_repo
        # Injectable so callers that already hold a ProjectService (and tests
        # that stub knowledge availability) do not build a second one.
        self._projects = (
            project_service if project_service is not None else ProjectService(services)
        )

    # ── definitions ──────────────────────────────────────────────────────────

    def list_tags(self, project_id: str, *, user: ProjectActor) -> list[ProjectTagRow]:
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_READ)
        return self._tags.list_by_project(project_id)

    def create_tag(
        self,
        project_id: str,
        *,
        user: ProjectActor,
        name: object,
        color: object = "",
    ) -> ProjectTagRow:
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_WRITE)
        clean_name = normalize_tag_name(name)
        clean_color = normalize_tag_color(color)
        # Pre-check so the common collision is a clean 409 rather than a driver
        # error; the UNIQUE(project_id, name) constraint stays as the backstop.
        if self._tags.find_by_name(project_id, clean_name) is not None:
            raise _tag_invalid(f"A tag named '{clean_name}' already exists in this project.")
        try:
            return self._tags.create(
                project_id=project_id,
                name=clean_name,
                color=clean_color,
                created_by=user.id,
            )
        except ValueError as exc:
            raise _tag_invalid(
                f"A tag named '{clean_name}' already exists in this project."
            ) from exc

    def update_tag(
        self,
        project_id: str,
        tag_id: str,
        *,
        user: ProjectActor,
        name: object = UNSET,
        color: object = UNSET,
    ) -> ProjectTagRow:
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_WRITE)
        tag = self._require_tag(project_id, tag_id)
        clean_name: object = UNSET
        if name is not UNSET:
            clean_name = normalize_tag_name(name)
            clash = self._tags.find_by_name(project_id, str(clean_name))
            if clash is not None and clash.tag_id != tag.tag_id:
                raise _tag_invalid(f"A tag named '{clean_name}' already exists in this project.")
        clean_color: object = UNSET
        if color is not UNSET:
            clean_color = normalize_tag_color(color)
        try:
            updated = self._tags.update(tag.tag_id, name=clean_name, color=clean_color)
        except ValueError as exc:
            raise _tag_invalid(
                f"A tag named '{clean_name}' already exists in this project."
            ) from exc
        if updated is None:
            raise _tag_invalid(f"Unknown tag: '{tag_id}'.")
        return updated

    def delete_tag(self, project_id: str, tag_id: str, *, user: ProjectActor) -> bool:
        """Delete a definition; its links disappear through the FK cascade."""
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_WRITE)
        tag = self._require_tag(project_id, tag_id)
        return self._tags.delete(tag.tag_id)

    # ── task links ───────────────────────────────────────────────────────────

    def set_task_tags(
        self,
        project_id: str,
        task_id: str,
        *,
        user: ProjectActor,
        tag_ids: Sequence[object],
    ) -> list[ProjectTagRow]:
        """Replace a task's tags (PLAN §4 ``PUT …/tasks/{tid}/tags``).

        The body is the **whole** set: a tag omitted from it is detached. A
        duplicate inside one request is rejected rather than silently collapsed,
        because it always means the caller built the list wrong.
        """
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_WRITE)
        self._projects.get_task(project_id, task_id, user=user)

        wanted = [str(value) for value in tag_ids]
        if len(set(wanted)) != len(wanted):
            raise _tag_invalid("The same tag was sent twice for one task.")

        # Every id must name a tag of *this* project: a tag from another project
        # is indistinguishable from a missing one to the caller.
        for tag_id in wanted:
            self._require_tag(project_id, tag_id)

        self._tags.set_task_tags(task_id, wanted)
        return self._resolve(wanted)

    def resolve_task_tags(self, task_ids: Sequence[str]) -> dict[str, list[ProjectTagRow]]:
        """Batch read for embedding tags in task responses.

        Permission is deliberately **not** re-checked here: callers reach this
        only after the task list has been authorized, and re-asserting per task
        would turn one query into N.
        """
        return self._tags.list_tags_for_tasks([str(task_id) for task_id in task_ids])

    # ── internals ────────────────────────────────────────────────────────────

    def _require_tag(self, project_id: str, tag_id: str) -> ProjectTagRow:
        tag = self._tags.get(tag_id)
        if tag is None or tag.project_id != project_id:
            raise _tag_invalid(f"Unknown tag: '{tag_id}'.")
        return tag

    def _resolve(self, tag_ids: Sequence[str]) -> list[ProjectTagRow]:
        """Definitions for ``tag_ids``, in the order the links were created."""
        by_id = {row.tag_id: row for row in self._tags.list_by_ids([str(t) for t in tag_ids])}
        return [by_id[tag_id] for tag_id in (str(t) for t in tag_ids) if tag_id in by_id]
