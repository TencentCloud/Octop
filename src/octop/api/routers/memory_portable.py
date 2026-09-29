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

from octop.api.common.agent import require_agent_owner_row
from octop.api.common.agent_workspace import resolve_agent_workspace_dir
from octop.api.common.content_disposition import content_disposition
from octop.api.common.memory_client import memory_db_path_for_cfg, memory_namespace
from octop.api.deps import current_user, get_server
from octop.infra.agents.memory.backend import (
    agent_memory_namespace,
    open_memory_kwargs,
)
from octop.infra.agents.memory.portable import (
    HOST_KIND_AGENT,
    assert_manifest_scope_is_safe,
    resolve_namespace_to_adopt,
)
from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)

router = APIRouter()

# ``agent_{agent_id}`` 的前缀不在本模块重复字面量：取**权威构造器**在空 id 上的输出
# （``infra/agents/memory/backend.py · agent_memory_namespace``）⇒ 权威改了这里自动跟随（T-62）。
_AGENT_NS_PREFIX = agent_memory_namespace("")


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
    """Portable pack/adopt is a SQLite-file mechanism; PostgreSQL memory has a
    different migration model.

    SQLite: one file per agent — pack/adopt moves that file's contents between
    hosts (Octop / OpenClaw / hermes).

    PostgreSQL: all agents share fixed tables in the ``octop_memory`` schema,
    isolated by a ``namespace`` column. There is no per-agent file to pack, and
    ``pg_dump`` of the schema must NOT be suggested as a substitute — it would
    export every agent's memory, not just this one. The supported way to give
    another host (e.g. OpenClaw) access is to point it at the same DSN and
    namespace, where the memory is simply shared rather than migrated.
    """
    workspace = resolve_agent_workspace_dir(server, agent_id)
    _ns, backend, _cfg = open_memory_kwargs(
        agent_id=agent_id,
        cfg=_agent_config_dict(server, agent_id),
        octop_config=server.services.config,
        workspace_dir=workspace,
    )
    if backend == "postgres":
        # no-details: 服务端自身状态/依赖缺失：无调用者可见标识可加（message 已是全部定位）
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            "portable memory pack/adopt only supports sqlite memory backends; "
            "this agent's memory lives in shared PostgreSQL tables (isolated by "
            "namespace), so there is no per-agent file to pack. To use this "
            "agent's memory from another host (e.g. OpenClaw), point that host "
            "at the same PostgreSQL DSN and namespace instead of migrating.",
            status=501,
        )


def _agent_memory_db_path(server: Any, agent_id: str) -> Path:
    """该 agent **真正被读**的记忆库文件 —— 复用唯一真源，覆盖两种布局。

    ``octop_memory`` 的 ``adopt()`` 自己推出的是 **legacy** 路径
    （``~/.octop/agents/{id}/memory.sqlite``，`…/adopter.py · _resolve_target_db_path @61-67`），
    而新布局 agent 的记忆库在 ``{workspace}/.octop/memory.sqlite``
    （``api/common/memory_client.py · memory_db_path_for_cfg @49`` → ``host_system_dir``）。
    不覆盖它，迁入的记忆就落到一个该 agent **永远不会读**的文件里。

    ``memory_db_path_for_cfg`` 同时覆盖两种布局：``host_system_dir`` 只在
    ``config_json.system_files_path`` 有值（新布局 = ``.octop``）时加前缀，legacy 配置下
    返回工作区目录本身 ⇒ ``{workspace}/memory.sqlite``。**不得**在此另拼 ``.octop``。
    """
    workspace = resolve_agent_workspace_dir(server, agent_id)
    return memory_db_path_for_cfg(workspace, _agent_config_dict(server, agent_id))


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class _AdoptRequest(BaseModel):
    target_host: str = Field(description="目标宿主：agent / openclaw / hermes，可带 namespace")
    target_namespace: str | None = Field(default=None, description="目标 namespace（可选）")
    on_conflict: str = Field(default="skip", description="冲突策略：skip / replace / raise")
    host_rewrite: str = Field(default="keep", description="host 重写策略：keep / target")
    dry_run: bool = Field(default=False, description="仅预检，不实际写入")


def _owned_agent_ids(server: Any, user: Any) -> set[str]:
    """调用方拥有的 agent id 集合（权威 = `agent_repo.list_by_user`）。"""
    rows = server.services.agent_repo.list_by_user(user.id)
    return {str(row.agent_id) for row in rows}


def _agent_id_of_namespace(namespace: str) -> str | None:
    """``agent_<agent_id>`` → ``<agent_id>``；不是 agent 命名空间则 ``None``。

    用 ``namespace``（= sqlite 表前缀，`…/sources.py · _list_namespaces @94`）而不是
    ``agent_name`` 做归属判据：后者是 ``db_path.parent.name``（`…/sources.py · _infer_agent_name @82-86`），
    对**新布局** ``~/.octop/agents/<id>/.octop/memory.sqlite`` 会退化成 ``".octop"``，不可靠。

    前缀不在这里重复字面量：**取自权威构造器**（空 id ⇒ 恰好是前缀），权威改了这里自动跟随（T-62）。
    """
    value = str(namespace or "").strip()
    prefix = _AGENT_NS_PREFIX
    if not value.startswith(prefix):
        return None
    return value[len(prefix) :].rstrip("_") or None


def _scoped_source_rows(
    raw: list[dict[str, Any]], *, owned: set[str], is_admin: bool
) -> list[dict[str, Any]]:
    """按调用方的作用域裁剪 sources 清单。

    * ``admin`` —— 主机级全量（含 ``db_path`` 绝对路径），与改动前一致。
    * 非 admin —— 只保留**自己拥有的 agent** 的条目，且**不返回绝对路径**
      （``db_path`` 会泄露本机 agent 存储布局）。
    """
    if is_admin:
        return raw
    out: list[dict[str, Any]] = []
    for row in raw:
        if str(row.get("host_kind") or "") != HOST_KIND_AGENT:
            continue
        agent_id = _agent_id_of_namespace(str(row.get("namespace") or ""))
        if agent_id is None or agent_id not in owned:
            continue
        out.append({key: value for key, value in row.items() if key != "db_path"})
    return out


def _read_manifest_or_value_error(pkg_path: Path) -> dict[str, Any]:
    """读上传包内的 ``manifest.json``。

    坏包**必须**仍映射成 400（改动前由 ``adopt()`` 自己的 ``_PKG_ERRORS`` 转成 ``ValueError``）。
    本函数在 ``adopt()`` 之前多读一次 manifest，若不在此归一异常类型，
    ``zipfile.BadZipFile`` / ``KeyError`` 会掉进路由的兜底 ``except Exception`` ⇒ 变成 500
    —— 那是本次修复引入的行为回归。
    """
    import zipfile

    from octop_memory.operations.migration.portable.packer import read_manifest

    try:
        return dict(read_manifest(pkg_path))
    except (zipfile.BadZipFile, OSError, ValueError, KeyError) as exc:
        # `json.JSONDecodeError` 是 `ValueError` 的子类，无需单列。
        raise ValueError(f"failed to read .hmpkg file {pkg_path}: {exc}") from exc


# ---------------------------------------------------------------------------
# GET /api/memory/portable/sources
# ---------------------------------------------------------------------------


@router.get("/memory/portable/sources")
async def list_portable_sources(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> JSONResponse:
    """List the migratable memory stores this caller may see.

    非管理员只看到**自己拥有的 agent** 的条目，且**不含** ``db_path`` 绝对路径；
    管理员仍是主机级全量（AUD-1）。
    """
    try:
        from octop_memory.operations.migration.portable import list_sources

        sources = list_sources()
        rows = _scoped_source_rows(
            [s.to_dict() for s in sources],
            owned=_owned_agent_ids(server, user),
            is_admin=bool(getattr(user, "is_admin", False)),
        )
        return JSONResponse(content={"sources": rows})
    except ImportError:
        # no-details: 服务端自身状态/依赖缺失：无调用者可见标识可加（message 已是全部定位）
        raise OctopError(
            ErrorCode.INTERNAL_ERROR, "octop-memory 未安装，无法使用记忆迁移功能"
        ) from None
    except Exception as exc:
        logger.exception("list_portable_sources failed")
        # no-details: 上游异常原文已在 message；入 details 触犯 SEC-4 黑名单（异常原文/上游响应原文）
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
    require_agent_owner_row(agent_id, user=user, as_user=as_user, server=server)
    _refuse_postgres_portable(server, agent_id)

    try:
        from octop_memory.operations.migration.portable import pack
        from octop_memory.operations.migration.portable.models import SourceInfo
        from octop_memory.operations.migration.portable.sources import _probe_db

        # Resolve the agent's db path and namespace
        workspace = resolve_agent_workspace_dir(server, agent_id)
        db_path = memory_db_path_for_cfg(workspace, _agent_config_dict(server, agent_id))
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
        # no-details: 服务端自身状态/依赖缺失：无调用者可见标识可加（message 已是全部定位）
        raise OctopError(ErrorCode.INTERNAL_ERROR, "octop-memory 未安装") from None
    except ValueError as exc:
        raise OctopError(ErrorCode.INTERNAL_ERROR, str(exc), status=400) from exc
    except Exception as exc:
        logger.exception("pack_agent_memory failed for agent_id=%s", agent_id)
        # no-details: 上游异常原文已在 message；入 details 触犯 SEC-4 黑名单（异常原文/上游响应原文）
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
    """Upload a .hmpkg file and import it into the target host.

    **命名空间作用域（AUD-2）**：本端点是设计四条写入路径之外的**第 5 条**，因此
    ``target_namespace`` / ``target_host`` 里的 ``host:namespace`` / **包内 manifest 的
    ``agent_name``** 三条通道在调用 ``adopt()`` **之前**一律过
    :func:`octop.infra.agents.memory.portable.resolve_namespace_to_adopt` 与
    :func:`octop.infra.agents.memory.portable.assert_manifest_scope_is_safe`
    —— 写盘之前拦，且 ``host_kind="agent"`` 时只允许写进该 agent 自己的命名空间。

    **目标文件（T-57）**：``host_kind="agent"`` 时把 :func:`_agent_memory_db_path` 算出的
    路径显式传给 ``adopt(target_db_path=…)``。不传的话 ``adopt()`` 会写进 legacy 布局的
    ``~/.octop/agents/{id}/memory.sqlite``，而新布局 agent 读的是
    ``{workspace}/.octop/memory.sqlite`` —— 功能上等于没迁。外部宿主
    （``openclaw`` / ``hermes`` / ``octopmemory``）的目标文件不归 Octop 管，保持
    ``adopt()`` 自己的解析（既有行为不变）。
    """
    require_agent_owner_row(agent_id, user=user, as_user=as_user, server=server)
    # ① 请求侧作用域：在产生任何副作用（读包 / 建临时文件 / 建目录）之前先判。
    _host_kind, scoped_namespace = resolve_namespace_to_adopt(
        agent_id=agent_id,
        target_host=target_host,
        target_namespace=target_namespace,
    )
    _refuse_postgres_portable(server, agent_id)
    # ② 目标文件：只有 agent 这条分支落在 Octop 自己的工作区树里，需要显式纠正。
    target_db_path: Path | None = (
        _agent_memory_db_path(server, agent_id) if _host_kind == HOST_KIND_AGENT else None
    )

    try:
        from octop_memory.operations.migration.portable import adopt

        # Write the uploaded file to a temp file
        with tempfile.NamedTemporaryFile(suffix=".hmpkg", delete=False) as tmp:
            content = await pkg_file.read()
            tmp.write(content)
            tmp.flush()
            tmp_path = Path(tmp.name)

        try:
            # ② 包侧作用域：`agent_name` 会经 `…/adopter.py · _build_target_namespace @267-268`
            # 流进写入路径，且**不需要任何表单字段**即可命中 ⇒ 一并校验。
            assert_manifest_scope_is_safe(_read_manifest_or_value_error(tmp_path))

            summary = adopt(
                tmp_path,
                target_host,
                target_namespace=scoped_namespace,
                on_conflict=on_conflict,
                host_rewrite=host_rewrite,
                dry_run=dry_run,
                target_db_path=target_db_path,
            )
        finally:
            tmp_path.unlink(missing_ok=True)

        return JSONResponse(content=summary.to_dict())

    except ImportError:
        # no-details: 服务端自身状态/依赖缺失：无调用者可见标识可加（message 已是全部定位）
        raise OctopError(ErrorCode.INTERNAL_ERROR, "octop-memory 未安装") from None
    except OctopError:
        # 作用域拒绝（400/403）与 "octop-memory 未安装" 必须原样上抛，
        # 不能被下面的兜底 Exception 改写成 500。
        raise
    except ValueError as exc:
        raise OctopError(ErrorCode.INTERNAL_ERROR, str(exc), status=400) from exc
    except Exception as exc:
        logger.exception("adopt_agent_memory failed for agent_id=%s", agent_id)
        # no-details: 上游异常原文已在 message；入 details 触犯 SEC-4 黑名单（异常原文/上游响应原文）
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
    require_agent_owner_row(agent_id, user=user, as_user=as_user, server=server)
    _refuse_postgres_portable(server, agent_id)

    try:
        from octop_memory.operations.migration.portable import doctor

        # Resolve the agent's db path
        workspace = resolve_agent_workspace_dir(server, agent_id)
        db_path = memory_db_path_for_cfg(workspace, _agent_config_dict(server, agent_id))

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
        # no-details: 服务端自身状态/依赖缺失：无调用者可见标识可加（message 已是全部定位）
        raise OctopError(ErrorCode.INTERNAL_ERROR, "octop-memory 未安装") from None
    except Exception as exc:
        logger.exception("doctor_agent_memory failed for agent_id=%s", agent_id)
        # no-details: 上游异常原文已在 message；入 details 触犯 SEC-4 黑名单（异常原文/上游响应原文）
        raise OctopError(ErrorCode.INTERNAL_ERROR, str(exc)) from exc


__all__ = ["router"]
