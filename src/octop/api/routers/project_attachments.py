"""HTTP surface for project attachments — staging, binding, download, delete.

Six routes from PLAN.md §7.4, all thin: the router reads the multipart body with
the shared capped reader, then ``ProjectAttachmentService`` owns the whitelist,
quota, storage layout and metadata. No response ever carries a stored name or an
absolute path.

Registration in ``api/app.py`` belongs to the integration task (T-INT).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from octop.api.common.upload_limit import read_upload_capped
from octop.api.deps import get_server, require_permission
from octop.infra.db.repos.project_artifacts import ArtifactRow
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.projects.attachments import ProjectAttachmentService
from octop.infra.server import OctopServer
from octop.infra.users.identity import User

router = APIRouter(prefix="/projects")


class AttachmentOut(BaseModel):
    """Attachment metadata. Deliberately no ``uri`` / path field."""

    artifact_id: str
    task_id: str | None = Field(description="Null while the attachment is staged.")
    name: str = Field(description="Original file name, for display only.")
    size: int
    mime: str
    created_at: int
    uploader: str = Field(description="Actor reference, e.g. user:12.")

    @classmethod
    def of(cls, row: ArtifactRow) -> AttachmentOut:
        return cls(
            artifact_id=row.artifact_id,
            task_id=row.task_id,
            name=row.name,
            size=row.size,
            mime=row.mime,
            created_at=row.created_at,
            uploader=row.created_by,
        )


class AttachmentBindBody(BaseModel):
    task_id: str | None = Field(default=None, description="Task to bind this staged attachment to.")
    comment_id: str | None = Field(
        default=None,
        description=(
            "Comment to bind this staged attachment to (v23). Exactly one of "
            "task_id / comment_id must be sent."
        ),
    )


def _attachment_service(server: OctopServer) -> ProjectAttachmentService:
    assert server.services is not None
    return ProjectAttachmentService(server.services)


async def _accept_upload(
    server: OctopServer,
    *,
    project_id: str,
    user: User,
    file: UploadFile,
    task_id: str | None,
) -> AttachmentOut:
    """Authorize, read within the cap, then store — the one upload path."""
    service = _attachment_service(server)
    service.precheck_upload(project_id, user=user, task_id=task_id)
    data = await read_upload_capped(
        file,
        max_bytes=service.max_file_bytes(),
        code=ErrorCode.PROJECT_ATTACHMENT_INVALID,
        status=413,
    )
    row = service.store(
        project_id,
        user=user,
        filename=file.filename,
        content_type=file.content_type,
        data=data,
        task_id=task_id,
    )
    return AttachmentOut.of(row)


@router.post(
    "/{project_id}/attachments",
    summary="Upload an attachment (staged)",
    status_code=status.HTTP_201_CREATED,
)
async def upload_project_attachment(
    project_id: str,
    file: UploadFile = File(..., description="File to stage; bound later on create."),
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> AttachmentOut:
    """Stage a file **before** its task exists — the create-task dialog's 📎 path.

    Allowed types are MIME + extension matched against one whitelist row; the
    stored name is generated server-side, so the client name is display-only.
    """
    return await _accept_upload(server, project_id=project_id, user=user, file=file, task_id=None)


@router.post(
    "/{project_id}/tasks/{task_id}/attachments",
    summary="Upload an attachment onto a task",
    status_code=status.HTTP_201_CREATED,
)
async def upload_task_attachment(
    project_id: str,
    task_id: str,
    file: UploadFile = File(..., description="File to attach to this task."),
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> AttachmentOut:
    """Same upload, bound immediately. A task of another project is a 404."""
    return await _accept_upload(
        server, project_id=project_id, user=user, file=file, task_id=task_id
    )


@router.patch("/{project_id}/attachments/{artifact_id}", summary="Bind a staged attachment")
async def bind_project_attachment(
    project_id: str,
    artifact_id: str,
    body: AttachmentBindBody,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> AttachmentOut:
    """Bind a **staged** attachment to a task ("create first, attach later").

    Re-binding an already-bound attachment is a 409: send it back to staging by
    deleting it instead (the file is never moved).
    """
    service = _attachment_service(server)
    if (body.task_id is None) == (body.comment_id is None):
        raise OctopError(
            ErrorCode.PROJECT_ATTACHMENT_INVALID,
            "send exactly one of task_id / comment_id",
        )
    if body.comment_id is not None:
        row = service.bind_to_comment(
            project_id, artifact_id, comment_id=body.comment_id, user=user
        )
    else:
        assert body.task_id is not None  # noqa: S101 - guarded by the check above
        row = service.bind_to_task(project_id, artifact_id, task_id=body.task_id, user=user)
    return AttachmentOut.of(row)


@router.get("/{project_id}/tasks/{task_id}/attachments", summary="List task attachments")
async def list_task_attachments(
    project_id: str,
    task_id: str,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> list[AttachmentOut]:
    """Oldest first. Names are not unique — two identical uploads are two rows."""
    rows = _attachment_service(server).list_for_task(project_id, task_id, user=user)
    return [AttachmentOut.of(row) for row in rows]


@router.get(
    "/{project_id}/attachments/{artifact_id}/download",
    summary="Download an attachment",
    response_class=FileResponse,
    responses={
        200: {
            "description": "The stored file, streamed.",
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
        }
    },
)
async def download_project_attachment(
    project_id: str,
    artifact_id: str,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> FileResponse:
    """Stream the file by id. Staged attachments are downloadable too."""
    row, path = _attachment_service(server).download(project_id, artifact_id, user=user)
    return FileResponse(
        path,
        media_type=row.mime or "application/octet-stream",
        filename=row.name,
    )


@router.delete("/{project_id}/attachments/{artifact_id}", summary="Delete an attachment")
async def delete_project_attachment(
    project_id: str,
    artifact_id: str,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> dict[str, Any]:
    """Delete the row **and** the file; staged and bound attachments both go."""
    deleted = _attachment_service(server).delete(project_id, artifact_id, user=user)
    return {"deleted": deleted}
