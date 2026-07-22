"""Cross-host memory migration service REST endpoint (requirements 1, 2, 3, 5, 8).

Mounted routes:
  GET  /api/memory/portable/sources
  POST /api/agents/{agent_id}/memory/portable/pack
  POST /api/agents/{agent_id}/memory/portable/adopt
  POST /api/agents/{agent_id}/memory/portable/doctor
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from octop.api.common.agent import require_agent_row
from octop.api.common.content_disposition import content_disposition
from octop.api.common.memory_client import memory_db_path, memory_namespace
from octop.api.deps import current_user, get_server
from octop.infra.agents.memory_backend import open_memory_kwargs
from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)

router = APIRouter()


def _agent_config_dict(server: Any, agent_id: str) -> dict[str, Any]:
    import json  # noqa: PLC0415

    row = server.services.agent_repo.get(agent_id)
    if row is None or not row.config_json:
        return {}
    try:
        parsed = json.loads(row.config_json)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _refuse_postgres_portable(server: Any, agent_id: str) -> None:
    workspace = server.services.paths.ensure_agent_workspace(agent_id)
    _ns, backend, _cfg = open_memory_kwargs(
        agent_id=agent_id,
        cfg=_agent_config_dict(server, agent_id),
        octop_config=server.services.config,
        workspace_dir=workspace,
    )
    if backend == "postgres":
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            "portable memory pack/adopt is not supported when memory.backend is postgres; "
            "use pg_dump on the memory schema instead",
            status=501,
        )


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class _AdoptRequest(BaseModel):
    target_host: str = Field(description="目标宿主：agent / openclaw / hermes，可带 namespace")
    target_namespace: str | None = Field(default=None, description="目标 namespace（可选）")
    on_conflict: str = Field(default="skip", description="冲突策略：skip / replace / raise")
    host_rewrite: str = Field(default="keep", description="host 重写策略：keep / target")
    dry_run: bool = Field(default=False, description="仅预检，不实际写入")


# ---------------------------------------------------------------------------
# GET /api/memory/portable/sources
# ---------------------------------------------------------------------------


@router.get("/memory/portable/sources")
async def list_portable_sources(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> JSONResponse:
    """List all migratable memory stores on this host."""
    try:
        from harness_memory.operations.migration.portable import list_sources

        sources = list_sources()
        return JSONResponse(content={"sources": [s.to_dict() for s in sources]})
    except ImportError:
        raise OctopError(
            ErrorCode.INTERNAL_ERROR, "harness-memory 未安装，无法使用记忆迁移功能"
        ) from None
    except Exception as exc:
        logger.exception("list_portable_sources failed")
        raise OctopError(ErrorCode.INTERNAL_ERROR, str(exc)) from exc


# ---------------------------------------------------------------------------
# POST /api/agents/{agent_id}/memory/portable/pack
# ---------------------------------------------------------------------------


@router.post("/agents/{agent_id}/memory/portable/pack")
async def pack_agent_memory(
    agent_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
    as_user: int | None = Query(default=None),
) -> StreamingResponse:
    """Package the agent's memory into a .hmpkg file and serve it as a download attachment."""
    require_agent_row(agent_id, user=user, as_user=as_user, server=server)
    _refuse_postgres_portable(server, agent_id)

    try:
        from harness_memory.operations.migration.portable import pack
        from harness_memory.operations.migration.portable.models import SourceInfo
        from harness_memory.operations.migration.portable.sources import _probe_db

        # Resolve the agent's db path and namespace
        workspace = server.services.paths.ensure_agent_workspace(agent_id)
        db_path = memory_db_path(workspace)
        ns = memory_namespace(agent_id)

        # Build SourceInfo
        sources = _probe_db(db_path, "agent")
        src = next((s for s in sources if s.namespace == ns), None)
        if src is None:
            # If not found, build a minimal one
            src = SourceInfo(
                host_kind="agent",
                db_path=str(db_path),
                namespace=ns,
                agent_name=agent_id,
            )

        # Package into a temp file
        with tempfile.NamedTemporaryFile(suffix=".hmpkg", delete=False) as tmp:
            tmp.flush()
            tmp_path = Path(tmp.name)

        summary = pack(src, out=tmp_path)

        # Read the file content and stream it back
        from datetime import UTC, datetime

        ts = datetime.now(UTC).strftime("%Y%m%d-%H%M")
        filename = f"{agent_id}-{ts}.hmpkg"

        def _iter_file() -> Any:
            with open(tmp_path, "rb") as f:
                while chunk := f.read(65536):
                    yield chunk
            tmp_path.unlink(missing_ok=True)

        return StreamingResponse(
            _iter_file(),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": content_disposition(filename),
                "X-Pack-Summary": str(summary.total_rows),
            },
        )

    except ImportError:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "harness-memory 未安装") from None
    except ValueError as exc:
        raise OctopError(ErrorCode.INTERNAL_ERROR, str(exc), status=400) from exc
    except Exception as exc:
        logger.exception("pack_agent_memory failed for agent_id=%s", agent_id)
        raise OctopError(ErrorCode.INTERNAL_ERROR, str(exc)) from exc


# ---------------------------------------------------------------------------
# POST /api/agents/{agent_id}/memory/portable/adopt
# ---------------------------------------------------------------------------


@router.post("/agents/{agent_id}/memory/portable/adopt")
async def adopt_agent_memory(
    agent_id: str,
    pkg_file: UploadFile = File(..., description=".hmpkg 文件"),
    target_host: str = Form(default="agent", description="目标宿主"),
    target_namespace: str | None = Form(default=None),
    on_conflict: str = Form(default="skip"),
    host_rewrite: str = Form(default="keep"),
    dry_run: bool = Form(default=False),
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
    as_user: int | None = Query(default=None),
) -> JSONResponse:
    """Upload a .hmpkg file and import it into the target host."""
    require_agent_row(agent_id, user=user, as_user=as_user, server=server)
    _refuse_postgres_portable(server, agent_id)

    try:
        from harness_memory.operations.migration.portable import adopt

        # Write the uploaded file to a temp file
        with tempfile.NamedTemporaryFile(suffix=".hmpkg", delete=False) as tmp:
            content = await pkg_file.read()
            tmp.write(content)
            tmp.flush()
            tmp_path = Path(tmp.name)

        try:
            summary = adopt(
                tmp_path,
                target_host,
                target_namespace=target_namespace,
                on_conflict=on_conflict,
                host_rewrite=host_rewrite,
                dry_run=dry_run,
            )
        finally:
            tmp_path.unlink(missing_ok=True)

        return JSONResponse(content=summary.to_dict())

    except ImportError:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "harness-memory 未安装") from None
    except ValueError as exc:
        raise OctopError(ErrorCode.INTERNAL_ERROR, str(exc), status=400) from exc
    except Exception as exc:
        logger.exception("adopt_agent_memory failed for agent_id=%s", agent_id)
        raise OctopError(ErrorCode.INTERNAL_ERROR, str(exc)) from exc


# ---------------------------------------------------------------------------
# POST /api/agents/{agent_id}/memory/portable/doctor
# ---------------------------------------------------------------------------


@router.post("/agents/{agent_id}/memory/portable/doctor")
async def doctor_agent_memory(
    agent_id: str,
    host_spec: str = Form(default="agent", description="目标宿主，格式：host 或 host:namespace"),
    compare_pkg: UploadFile | None = File(default=None, description="可选的 .hmpkg 文件用于比对"),
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
    as_user: int | None = Query(default=None),
) -> JSONResponse:
    """Run a health check against the target db."""
    require_agent_row(agent_id, user=user, as_user=as_user, server=server)
    _refuse_postgres_portable(server, agent_id)

    try:
        from harness_memory.operations.migration.portable import doctor

        # Resolve the agent's db path
        workspace = server.services.paths.ensure_agent_workspace(agent_id)
        db_path = memory_db_path(workspace)

        # Handle the optional comparison package
        compare_path: Path | None = None
        tmp_compare: Path | None = None
        if compare_pkg is not None:
            with tempfile.NamedTemporaryFile(suffix=".hmpkg", delete=False) as tmp:
                content = await compare_pkg.read()
                tmp.write(content)
                tmp.flush()
                tmp_compare = Path(tmp.name)
            compare_path = tmp_compare

        try:
            report = doctor(
                host_spec,
                db_path=str(db_path),
                compare_with=compare_path,
            )
        finally:
            if tmp_compare:
                tmp_compare.unlink(missing_ok=True)

        return JSONResponse(content=report.to_dict())

    except ImportError:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "harness-memory 未安装") from None
    except Exception as exc:
        logger.exception("doctor_agent_memory failed for agent_id=%s", agent_id)
        raise OctopError(ErrorCode.INTERNAL_ERROR, str(exc)) from exc


__all__ = ["router"]
