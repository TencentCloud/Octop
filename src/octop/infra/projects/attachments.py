"""Project attachment storage — staging, binding, quota, and safe file names.

The contract is PLAN.md §7 (frozen): one metadata table (``project_artifacts``,
kind ``attachment``), a MIME+extension whitelist where **both** must hit the same
row, server-generated stored names, per-file / per-task / per-project quota, and a
staging state (``task_id IS NULL``) so the create-task dialog can upload before the
task exists.

The HTTP layer reads the request body (``api/common/upload_limit.py``) and hands
the bytes over — infra never imports ``api/``. Everything else (whitelist, quota,
storage layout, metadata) lives here, and every entry point is guarded by
``ProjectService.assert_project_role`` — there is no second permission path.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from urllib.parse import unquote

from octop.infra.db.repos._base import now_ts
from octop.infra.db.repos.project_artifacts import ATTACHMENT_KIND, ArtifactRow
from octop.infra.db.services import SharedServices
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.projects.service import PROJECT_READ, PROJECT_WRITE, ProjectActor, ProjectService
from octop.infra.utils.ulid import new_short_id

logger = logging.getLogger(__name__)

#: Per-task total (frozen, PLAN.md §7.2).
PROJECT_TASK_ATTACHMENT_TOTAL_MAX_BYTES = 200 * 1024 * 1024
#: Per-project pending (staged) total (frozen, PLAN.md §7.2).
PROJECT_PENDING_ATTACHMENT_MAX_BYTES = 200 * 1024 * 1024
#: Staged rows older than this are collected lazily on the next write request.
PENDING_TTL_SECONDS = 24 * 3600
#: Retry budget for an attachment id that collides in the DB or on disk.
_ID_ATTEMPTS = 16
_MAX_NAME_CHARS = 255
_STORED_NAME = re.compile(r"^[A-Za-z0-9]{4,16}\.[A-Za-z0-9]{1,8}$")
_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")

#: MIME -> allowed extensions (PLAN.md §7.3). Execution-capable types are absent
#: by design: html / svg / javascript / anything ``x-executable`` or ``x-sh``.
ALLOWED_ATTACHMENT_TYPES: dict[str, tuple[str, ...]] = {
    "application/pdf": (".pdf",),
    "image/png": (".png",),
    "image/jpeg": (".jpg", ".jpeg"),
    "image/gif": (".gif",),
    "image/webp": (".webp",),
    "text/plain": (".txt",),
    "text/markdown": (".md",),
    "text/csv": (".csv",),
    "application/json": (".json",),
    "application/zip": (".zip",),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (".docx",),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": (".xlsx",),
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": (".pptx",),
}


def _attachment_invalid(message: str, *, status: int = 0) -> OctopError:
    return OctopError(ErrorCode.PROJECT_ATTACHMENT_INVALID, message, status=status)


def _too_large(message: str) -> OctopError:
    return _attachment_invalid(message, status=413)


def _normalize_mime(raw: str | None) -> str:
    """``text/plain; charset=utf-8`` -> ``text/plain``."""
    return (raw or "").split(";", 1)[0].strip().lower()


def _check_client_name(filename: str | None) -> str:
    """Reject traversal before anything touches the filesystem.

    Only the *display* name comes from user input; the stored name never does.
    Encoded variants (``%2e%2e%2f``) are decoded first, then the same rules apply.
    """
    raw = (filename or "").strip()
    if not raw:
        raise _attachment_invalid("attachment is missing a file name")
    for candidate in (raw, unquote(raw), unquote(unquote(raw))):
        normalized = candidate.replace("\\", "/")
        if "\x00" in candidate:
            raise _attachment_invalid("attachment file name is not allowed")
        if "/" in normalized or "\\" in candidate:
            raise _attachment_invalid("attachment file name is not allowed")
        if _DRIVE_PREFIX.match(normalized) or normalized in ("..", "."):
            raise _attachment_invalid("attachment file name is not allowed")
    cleaned = "".join(ch for ch in raw if ch.isprintable()).strip()
    return cleaned[:_MAX_NAME_CHARS] or "attachment"


def _match_extension(filename: str, mime: str) -> str:
    """Return the canonical extension, or reject when MIME and suffix disagree."""
    suffix = Path(filename).suffix.lower()
    allowed = ALLOWED_ATTACHMENT_TYPES.get(mime)
    if allowed is None or suffix not in allowed:
        raise _attachment_invalid("attachment type is not allowed")
    return allowed[0]


class ProjectAttachmentService:
    def __init__(
        self, services: SharedServices, *, project_service: ProjectService | None = None
    ) -> None:
        self._services = services
        self._projects = project_service or ProjectService(services)
        self._repo = services.project_artifact_repo
        # v23: comments own attachments; the comment must exist in this project.
        self._comments = getattr(services, "project_comment_repo", None)

    # ── storage ──────────────────────────────────────────────────────────────

    def max_file_bytes(self) -> int:
        """Single-file cap from config (``max_upload_mb``, default 100MB)."""
        return self._services.config.max_upload_bytes

    def attachments_dir(self, project_id: str) -> Path:
        return self._services.paths.projects_dir / project_id / "attachments"

    def _ensure_dir(self, project_id: str) -> Path:
        out = self.attachments_dir(project_id)
        out.mkdir(parents=True, exist_ok=True)
        return out

    def _relative_uri(self, project_id: str, stored_name: str) -> str:
        return f"projects/{project_id}/attachments/{stored_name}"

    def _absolute_path(self, project_id: str, uri: str) -> Path:
        """Resolve a stored name safely — the row's uri never escapes the project."""
        stored_name = uri.rsplit("/", 1)[-1]
        if not _STORED_NAME.match(stored_name):
            raise OctopError(ErrorCode.NOT_FOUND, "Attachment file not found.")
        directory = self.attachments_dir(project_id)
        path = directory / stored_name
        if not path.resolve().is_relative_to(directory.resolve()):
            raise OctopError(ErrorCode.NOT_FOUND, "Attachment file not found.")
        return path

    def _store_bytes(self, project_id: str, *, data: bytes, extension: str) -> tuple[str, str]:
        """Write *data* under a freshly minted id; returns ``(artifact_id, uri)``.

        The id is generated once per attempt and used for **both** the row and the
        file name; an exclusive create (``xb``) turns an on-disk collision into a
        retry rather than an overwrite (PLAN.md §7.5.9).
        """
        directory = self._ensure_dir(project_id)
        resolved_root = directory.resolve()
        for _ in range(_ID_ATTEMPTS):
            artifact_id = new_short_id()
            if self._repo.artifact_id_exists(artifact_id):
                continue
            stored_name = f"{artifact_id}{extension}"
            path = directory / stored_name
            try:
                with open(path, "xb") as handle:
                    handle.write(data)
            except FileExistsError:
                continue
            if not path.resolve().is_relative_to(resolved_root):
                path.unlink(missing_ok=True)
                raise _attachment_invalid("attachment path escaped its project directory")
            return artifact_id, self._relative_uri(project_id, stored_name)
        raise RuntimeError("failed to allocate a unique attachment id")

    # ── staging lifecycle ────────────────────────────────────────────────────

    def collect_expired_pending(self, project_id: str) -> int:
        """Drop staged rows older than the TTL, files first (PLAN.md §7.5.6)."""
        cutoff = now_ts() - PENDING_TTL_SECONDS
        removed = 0
        for row in self._repo.list_pending(project_id):
            if row.created_at >= cutoff:
                continue
            self._absolute_path(project_id, row.uri).unlink(missing_ok=True)
            if self._repo.delete(row.artifact_id):
                removed += 1
        return removed

    # ── write entry points ───────────────────────────────────────────────────

    def precheck_upload(
        self, project_id: str, *, user: ProjectActor, task_id: str | None = None
    ) -> None:
        """Authorize the upload *before* the body is read, and age out old stages."""
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_WRITE)
        if task_id is not None:
            self._require_task(project_id, task_id)
        self.collect_expired_pending(project_id)

    def store(
        self,
        project_id: str,
        *,
        user: ProjectActor,
        filename: str | None,
        content_type: str | None,
        data: bytes,
        task_id: str | None = None,
    ) -> ArtifactRow:
        """Validate and persist one uploaded file; ``task_id=None`` stages it."""
        self.precheck_upload(project_id, user=user, task_id=task_id)
        display_name = _check_client_name(filename)
        mime = _normalize_mime(content_type)
        extension = _match_extension(display_name, mime)
        self._assert_quota(project_id, task_id=task_id, incoming=len(data))

        artifact_id, uri = self._store_bytes(project_id, data=data, extension=extension)
        try:
            return self._repo.insert(
                artifact_id=artifact_id,
                project_id=project_id,
                task_id=task_id,
                name=display_name,
                uri=uri,
                size=len(data),
                mime=mime,
                file_hash=hashlib.sha256(data).hexdigest(),
                created_by=f"user:{user.id}",
            )
        except Exception:
            # A row we cannot describe must not leave an orphan file behind.
            self._absolute_path(project_id, uri).unlink(missing_ok=True)
            raise

    def _assert_quota(self, project_id: str, *, task_id: str | None, incoming: int) -> None:
        if task_id is None:
            used = self._repo.sum_pending_size(project_id)
            if used + incoming > PROJECT_PENDING_ATTACHMENT_MAX_BYTES:
                raise _too_large("this project's staged attachments are over the limit")
            return
        used = self._repo.sum_size_for_task(task_id)
        if used + incoming > PROJECT_TASK_ATTACHMENT_TOTAL_MAX_BYTES:
            raise _too_large("this task's attachments are over the limit")

    # ── binding ──────────────────────────────────────────────────────────────

    def bind_pending(
        self,
        project_id: str,
        task_id: str,
        artifact_ids: list[str],
        *,
        user: ProjectActor,
    ) -> list[ArtifactRow]:
        """Bind staged attachments to a task; re-checks the per-task quota."""
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_WRITE)
        self._require_task(project_id, task_id)
        return [self._bind_one(project_id, aid, task_id=task_id) for aid in artifact_ids]

    def _bind_one(self, project_id: str, artifact_id: str, *, task_id: str) -> ArtifactRow:
        row = self._repo.get(artifact_id)
        if row is None or row.project_id != project_id or row.kind != ATTACHMENT_KIND:
            raise OctopError(ErrorCode.NOT_FOUND, "Attachment not found.")
        if row.task_id is not None:
            raise _attachment_invalid("this attachment is already bound to a task", status=409)
        if self._repo.sum_size_for_task(task_id) + row.size > (
            PROJECT_TASK_ATTACHMENT_TOTAL_MAX_BYTES
        ):
            raise _too_large("this task's attachments are over the limit")
        if not self._repo.bind(artifact_id, task_id=task_id):
            raise _attachment_invalid("this attachment is already bound to a task", status=409)
        current = self._repo.get(artifact_id)
        if current is None:  # pragma: no cover - row deleted between two statements
            raise OctopError(ErrorCode.NOT_FOUND, "Attachment not found.")
        return current

    def _bind_comment_one(
        self, project_id: str, artifact_id: str, *, comment_id: str
    ) -> ArtifactRow:
        """Same shape as ``_bind_one`` for the comment column (v23).

        "Already bound" is a 409 here too: an artifact has exactly one
        ``comment_id``, so binding it to a second comment would be a silent
        re-bind — the endpoint would mean two different things depending on state.
        """
        row = self._repo.get(artifact_id)
        if row is None or row.project_id != project_id or row.kind != ATTACHMENT_KIND:
            raise OctopError(ErrorCode.NOT_FOUND, "Attachment not found.")
        if row.comment_id is not None:
            raise _attachment_invalid("this attachment is already bound to a comment", status=409)
        comment = self._comments.get(comment_id) if self._comments is not None else None
        if comment is None or comment.project_id != project_id:
            raise OctopError(ErrorCode.NOT_FOUND, "Comment not found in this project.")
        if not self._repo.bind_comment(artifact_id, comment_id=comment_id):
            raise _attachment_invalid("this attachment is already bound to a comment", status=409)
        current = self._repo.get(artifact_id)
        if current is None:  # pragma: no cover - row deleted between two statements
            raise OctopError(ErrorCode.NOT_FOUND, "Attachment not found.")
        return current

    def bind_to_comment(
        self, project_id: str, artifact_id: str, *, comment_id: str, user: ProjectActor
    ) -> ArtifactRow:
        """Bind a staged attachment to the comment that introduced it."""
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_WRITE)
        return self._bind_comment_one(project_id, artifact_id, comment_id=comment_id)

    def bind_to_task(
        self, project_id: str, artifact_id: str, *, task_id: str, user: ProjectActor
    ) -> ArtifactRow:
        """Explicit bind / re-bind path (``PATCH``); already-bound rows are 409."""
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_WRITE)
        self._require_task(project_id, task_id)
        return self._bind_one(project_id, artifact_id, task_id=task_id)

    def unbind_all(self, task_id: str, artifact_ids: list[str]) -> int:
        """Compensation helper: return rows to *pending*, never deleting files."""
        return sum(1 for aid in artifact_ids if self._repo.unbind(aid, task_id=task_id))

    # ── reads / delete ───────────────────────────────────────────────────────

    def list_for_task(
        self, project_id: str, task_id: str, *, user: ProjectActor
    ) -> list[ArtifactRow]:
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_READ)
        self._require_task(project_id, task_id)
        return self._repo.list_by_task(project_id=project_id, task_id=task_id)

    def download(
        self, project_id: str, artifact_id: str, *, user: ProjectActor
    ) -> tuple[ArtifactRow, Path]:
        row = self._require_row(project_id, artifact_id, user=user, required=PROJECT_READ)
        path = self._absolute_path(project_id, row.uri)
        if not path.is_file():
            raise OctopError(ErrorCode.NOT_FOUND, "Attachment file not found.")
        return row, path

    def delete(self, project_id: str, artifact_id: str, *, user: ProjectActor) -> bool:
        row = self._require_row(project_id, artifact_id, user=user, required=PROJECT_WRITE)
        self._absolute_path(project_id, row.uri).unlink(missing_ok=True)
        return self._repo.delete(artifact_id)

    def _require_row(
        self, project_id: str, artifact_id: str, *, user: ProjectActor, required: str
    ) -> ArtifactRow:
        self._projects.assert_project_role(project_id, user=user, required=required)
        row = self._repo.get(artifact_id)
        if row is None or row.project_id != project_id or row.kind != ATTACHMENT_KIND:
            raise OctopError(ErrorCode.NOT_FOUND, "Attachment not found.")
        return row

    # ── internals ────────────────────────────────────────────────────────────

    def _require_task(self, project_id: str, task_id: str) -> None:
        """A task id from another project must not be addressable (404, not 403)."""
        task = self._services.project_task_repo.get(task_id)
        if task is None or task.project_id != project_id:
            raise OctopError(ErrorCode.NOT_FOUND, "Task not found.")
