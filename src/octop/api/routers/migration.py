"""LightClaw → Octop migration import API."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile

from octop.api.deps import current_user, get_server
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.migration.finnie_importer import run_import

logger = logging.getLogger(__name__)

router = APIRouter()

# Maximum accepted upload size for a migration archive: 512 MB.
_MAX_ARCHIVE_BYTES = 512 * 1024 * 1024


@router.post(
    "/admin/migration/import-lightclaw",
    summary="Import a LightClaw migration archive",
    description=(
        "Upload a ``lightclaw_octop_migration_*.zip`` exported from LightClaw. "
        "Creates a new agent and imports workspace files, session history, "
        "uploads, and cron jobs. "
        "Provider and channel configuration are not imported and must be set up manually in Octop after import."
    ),
    tags=["admin"],
)
async def import_lightclaw(
    file: UploadFile = File(..., description="Migration ZIP archive"),  # noqa: B008
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Import a LightClaw migration archive for the current user."""
    assert server.services is not None

    raw = await file.read()
    if not raw:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "empty archive")
    if len(raw) > _MAX_ARCHIVE_BYTES:
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            f"archive too large (max {_MAX_ARCHIVE_BYTES // (1024**2)} MB)",
        )

    services = server.services
    report = await run_import(
        raw,
        user_id=user.id,
        paths=services.paths,
        agent_repo=services.agent_repo,
        cron_repo=services.cron_repo,
        thread_repo=services.thread_repo,
        session_repo=services.session_repo,
        user_repo=services.user_repo,
    )

    if report.has_errors:
        raise OctopError(
            ErrorCode.INTERNAL_ERROR,
            f"Import completed with errors: {'; '.join(report.errors[:3])}",
        )

    return {"ok": True, **report.to_dict()}
