"""Workspace router — read/write into a running agent's workspace."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from octop_harness.backends.utils import BackendOperationNotSupportedError
from octop_harness.backends.workspace import BackendWorkspace
from pydantic import BaseModel

from octop.api.common.agent_workspace import resolve_agent_workspace_dir
from octop.api.common.content_disposition import content_disposition
from octop.api.common.workspace import (
    coerce_read_content,
    file_info_to_dict,
    reanchor_entry_path,
    require_agent_workspace,
    require_running_workspace,
    workspace_api_path,
)
from octop.api.deps import current_user, get_server
from octop.infra.backup.workspace_archive import export_workspace_zip, import_workspace_zip
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.media.backend_files import (
    backend_workspace_path,
    is_allowed_host_download_abs_path,
    is_host_absolute_path,
    resolve_preview_payload,
)
from octop.infra.utils.doc_edit import DocConverter, get_doc_converter

logger = logging.getLogger(__name__)

_PROTECTED_PREFIX = "_builtin_skills"


# Team memory surface (B-19-A): owned by the team runtime, not by REST writers.
_TEAM_MEMORY_PREFIX = ".octop/team"


def _normalize_rel_posix(path: str) -> str:
    """Fold ``path`` into a workspace-relative POSIX form for prefix checks.

    Shared by both guards so their path judgements cannot drift: ``\\`` folds to
    ``/`` first (Windows spellings are then judged on the same components), then
    ``.`` / ``..`` / repeated ``/`` fold away and any leading/trailing ``/`` drops.
    """
    parts: list[str] = []
    for part in path.replace("\\", "/").split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


_ASCII_FOLD = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


def _fold_segment(seg: str) -> str:
    """★ 段折叠（唯一折点）= **ASCII 大小写折叠**（PLAN §2.2 · 用户拍板 ①）。

    ★ **不做** Unicode 归一（NFC/NFD）：保护名全 ASCII（``.octop`` / ``team`` /
    ``_builtin_skills``）⇒ 归一化对本判据零拒绝力。折叠是**收紧**（fail-closed）：大小写
    敏感卷上 ``_BUILTIN_SKILLS/x`` 本是另一个目录 ⇒ 拒绝是有意为之。
    """
    return seg.translate(_ASCII_FOLD)


def _protected_write_segments(io_path: str) -> list[str]:
    """有效后端目标的归一化 + 折叠段序列 —— 判据的唯一内核（不得再写第二份段比较）。"""
    rel = _normalize_rel_posix(io_path)
    return [_fold_segment(seg) for seg in rel.split("/") if seg]


def _team_memory_pair_hit(segments: list[str]) -> bool:
    """相邻段对 ``(".octop", "team")``（作用于**折叠后**段）。"""
    return any(
        segments[i] == ".octop" and segments[i + 1] == "team" for i in range(len(segments) - 1)
    )


def _builtin_skills_hit(segments: list[str]) -> bool:
    """★ 精确两形状：① 首段 == ``_builtin_skills``；② 相邻段对 ``(".octop", "_builtin_skills")``。

    ★ **不得**用「任一段相等」的粗口径：那会把 ``notes/_builtin_skills/x`` 由放行变 403。
    """
    return segments[:1] == [_PROTECTED_PREFIX] or any(
        segments[i] == ".octop" and segments[i + 1] == _PROTECTED_PREFIX
        for i in range(len(segments) - 1)
    )


def _relativize_to_workspace(io_path: str, workspace_dir: str | Path | None) -> str:
    """★ 主机绝对形态 ⇒ 先**相对工作区根**，再套既有精确两形状（contract：`file://` 不豁免）。

    ``file://`` 与主机绝对拼写经 ``_workspace_io_path`` 后带盘符/用户前缀（首段 == `/` 后的
    前缀），两形状都不命中 ⇒ 必须剥掉工作区根前缀后再判。★ 判据仍是既有两形状，**不**放宽成
    「任一段相等」（那会把 ``notes/_builtin_skills/x.md`` 由放行变 403）。

    工作区根不可得 / 目标本就是相对形态 / 目标在工作区根**之外** ⇒ 原样返回（越界由
    ``_assert_workspace_write_resolved`` 的解析分支兜底）。按**路径分量**相对化，故
    ``/data/ws_backup`` 不会被 ``/data/ws`` 误判为工作区内。
    """
    if workspace_dir is None or str(workspace_dir) == "":
        return io_path
    root = Path(str(workspace_dir)).expanduser()
    target = Path(io_path)
    if not root.is_absolute() or not target.is_absolute():
        return io_path
    try:
        rel = target.resolve(strict=False).relative_to(root.resolve(strict=False))
    except (OSError, RuntimeError, ValueError):
        return io_path
    return rel.as_posix()


def _assert_write_target_allowed(io_path: str, *, workspace_dir: str | Path | None = None) -> str:
    """★ 判据唯一落点：作用于**有效目标**串（根 / team 面 / builtin 面），返回同一串。

    顺序冻结（PLAN §2.3）：根分支最先 ⇒ team 面次之 ⇒ builtin 面最后。拒绝文案只含常量
    段，**不回显** ``path``（沿用 ``_map_workspace_fs_error`` 的防主机结构泄漏约定）。
    ``workspace_dir`` 只用于把主机绝对目标**相对化**后再判（见 ``_relativize_to_workspace``）；
    返回值恒为 ``io_path`` 原串 ⇒ 落盘目标不因判据而变。
    """
    judged = _relativize_to_workspace(io_path, workspace_dir)
    segments = _protected_write_segments(judged)
    if judged == "." or not segments:  # ★ 既有 workspace root 分支必须保留
        raise OctopError(ErrorCode.FORBIDDEN, "cannot modify workspace root")
    if _team_memory_pair_hit(segments):
        raise OctopError(
            ErrorCode.TEAM_ARTIFACT_OWNERSHIP_DENIED,
            f"cannot modify {_TEAM_MEMORY_PREFIX!r} paths",
        )
    if _builtin_skills_hit(segments):
        raise OctopError(ErrorCode.FORBIDDEN, f"cannot modify {_PROTECTED_PREFIX!r} paths")
    return io_path


def _assert_workspace_write_allowed(
    path: str, *, from_workspace: bool, workspace_dir: str | Path | None = None
) -> str:
    """★ 唯一入口：判根 / 两个受保护面，**返回有效后端目标 = 调用者必须落盘的那个串**。

    先 ``_workspace_io_path`` 取有效目标（`file://` 与主机绝对形态**不豁免**），再归一化 +
    ASCII 折叠后判两面 ⇒ 三拼写（相对 / 主机绝对 / ``file://``）同判同码。

    ★ ``workspace_dir``（调用点已有 ``ws.workspace_dir``）**必传**：主机绝对目标先相对化再判，
    否则带主机前缀的两形状不命中 ⇒ ``file://…/_builtin_skills/x`` 会漏判放行。
    """
    io_path = _workspace_io_path(path, from_workspace=from_workspace)
    return _assert_write_target_allowed(io_path, workspace_dir=workspace_dir)


def _assert_team_memory_writable(path: str, *, from_workspace: bool = False) -> str:
    """Reject writes whose **effective backend target** is team memory (``.octop/team/**``).

    Returns the resolved I/O path so the caller writes to *exactly* the string this
    guard just judged (same ``_workspace_io_path`` call, same ``from_workspace``).

    The judgement is made on the resolved target rather than on the raw argument,
    because the raw argument can reach the same file by three different spellings:

    * workspace-relative ``.octop/team/**``;
    * host-absolute ``/…/.octop/team/**`` (``from_workspace=false``, the default);
    * ``file:///…/.octop/team/**`` (``file://`` always resolves host-absolute).

    Criterion: the normalized target contains the **adjacent segment pair**
    ``(".octop", "team")`` at any position (any prefix + ``/.octop/team`` + optional
    trailing segments). A relative prefix test (``posix.startswith(".octop/team")``)
    is not enough: it only sees the workspace-relative spelling, while the two
    absolute spellings carry a host prefix before the pair (``Users/…/.octop/team/…``,
    ``file:/…/.octop/team/…``) and would slip through. The pair test needs no
    knowledge of the caller's arguments, so it holds for all three at once; and it
    stays precise — ``.octop/sessions/…`` / ``.octop/auth/…`` are not ``.octop/team``
    and keep passing.
    """
    io_path = _workspace_io_path(path, from_workspace=from_workspace)
    if _team_memory_pair_hit(_protected_write_segments(io_path)):
        raise OctopError(
            ErrorCode.TEAM_ARTIFACT_OWNERSHIP_DENIED,
            f"cannot modify {_TEAM_MEMORY_PREFIX!r} paths",
        )
    return io_path


def _assert_workspace_mutable(path: str) -> str:
    """Mutating ops always treat paths as workspace-relative (``from_workspace=true``)."""
    rel = _workspace_io_path(path, from_workspace=True)
    if rel == ".":
        raise OctopError(ErrorCode.FORBIDDEN, "cannot modify workspace root")
    # SEC-10: judge the *normalized* path so ``./`` / ``x/../`` / ``//`` cannot bypass.
    if _builtin_skills_hit(_protected_write_segments(rel)):
        raise OctopError(ErrorCode.FORBIDDEN, f"cannot modify {_PROTECTED_PREFIX!r} paths")
    return rel


_GUARD_RESOLVE_SKIPPED = "workspace-guard-resolve-skipped"
_GUARD_RESOLVE_OUTSIDE = "workspace-guard-resolve-outside"
_GUARD_RESOLVE_ERROR = "workspace-guard-resolve-error"


def _host_resolve_enabled(workspace: BackendWorkspace) -> bool:
    """★ 解析闸门（唯一判据源）：**只有拿到后端类型信息**且该后端是宿主路径类 ⇒ True。

    读口 = 调用点已有的 ``workspace`` 对象（``BackendWorkspace.workspace_dir`` 是 public
    property）。宿主路径类 = harness 本地后端（``FilesystemBackend`` 及其子类
    ``HarnessLocalShellBackend`` / ``BubbledLocalShellBackend``）；云端虚拟键（COS/S3/OSS/
    OBS）· docker / opensandbox 沙箱 · composite / state / store ⇒ False。
    ★ 本函数只读**类型信息**做「能否解析」闸门，**不**在此复制任何路径规则。
    """
    backend = getattr(workspace, "backend", None)
    if backend is None:
        return False
    try:
        from deepagents.backends.filesystem import FilesystemBackend
    except ImportError:  # pragma: no cover - 拿不到后端类型信息 ⇒ 闸门关
        return False
    return isinstance(backend, FilesystemBackend)


def _assert_workspace_write_resolved(
    io_path: str, *, workspace_dir: str | Path | None, resolve_ok: bool
) -> str:
    """★ 相位 B：闸门开 ⇒ 真实解析后再判一次；闸门关 ⇒ **不解析**、按文本口径判。

    ★ **绝不**把「解析不了」实现成放行。闸门关（远端 / docker / 拿不到后端类型信息 / 宿主
    根不可得）⇒ 不解析，仍走 ``_assert_write_target_allowed`` 的根 + 两面判据后**原样返回
    入参**，并留痕 ``_GUARD_RESOLVE_SKIPPED`` —— ★ **逐字登记：符号链接面未覆盖**（闸门关
    时软链别名判不出）。解析抛 ``OSError`` / ``RuntimeError`` ⇒ 403 ``cannot resolve write
    target``（token ``_GUARD_RESOLVE_ERROR``）；解析成功但越出工作区根 ⇒ 403 ``cannot
    modify paths outside the workspace``（token ``_GUARD_RESOLVE_OUTSIDE``）。解析成功且未
    命中 ⇒ 返回**解析后的相对串**（= 调用者落盘串）。留痕只进日志、**不进**错误体。
    """
    if not resolve_ok or workspace_dir is None or str(workspace_dir) == "":
        logger.warning(
            "%s io_path=%s symlink surface uncovered (text-only judgement)",
            _GUARD_RESOLVE_SKIPPED,
            io_path,
        )
        return _assert_write_target_allowed(io_path, workspace_dir=workspace_dir)
    root = Path(str(workspace_dir)).expanduser()
    if not root.is_absolute():  # 闸门开的前置 = 宿主根可得
        logger.warning(
            "%s io_path=%s symlink surface uncovered (text-only judgement)",
            _GUARD_RESOLVE_SKIPPED,
            io_path,
        )
        return _assert_write_target_allowed(io_path, workspace_dir=workspace_dir)
    resolved_root = root.resolve(strict=False)
    target = Path(io_path)
    if not target.is_absolute():
        target = resolved_root / _normalize_rel_posix(io_path)
    try:
        resolved = target.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        logger.warning("%s io_path=%s", _GUARD_RESOLVE_ERROR, io_path)
        raise OctopError(ErrorCode.FORBIDDEN, "cannot resolve write target") from None
    try:
        rel = resolved.relative_to(resolved_root).as_posix()
    except ValueError:
        logger.warning("%s io_path=%s", _GUARD_RESOLVE_OUTSIDE, io_path)
        raise OctopError(ErrorCode.FORBIDDEN, "cannot modify paths outside the workspace") from None
    return _assert_write_target_allowed(rel)


def _map_workspace_fs_error(exc: Exception, *, operation: str, path: str) -> OctopError:
    if isinstance(exc, BackendOperationNotSupportedError):
        return OctopError(ErrorCode.WORKSPACE_OP_UNSUPPORTED, str(exc))
    if isinstance(exc, FileNotFoundError):
        return OctopError(ErrorCode.NOT_FOUND, f"cannot {operation} {path!r}: not found")
    if isinstance(exc, FileExistsError):
        return OctopError(ErrorCode.SLASH_BAD_ARGS, str(exc))
    if isinstance(exc, PermissionError):
        return OctopError(ErrorCode.FORBIDDEN, str(exc))
    if isinstance(exc, ValueError):
        return OctopError(ErrorCode.SLASH_BAD_ARGS, str(exc))
    # ★ T-75：把**调用者给出的操作名**放进 details（i18n 会整条替换 message ⇒ 定位只能靠 details）。
    # ⛔ 有意**不**放 `path`：它可能是不透明/主机绝对路径，触犯 SEC-4 黑名单（主机绝对路径）。
    return OctopError(
        ErrorCode.INTERNAL_ERROR,
        f"cannot {operation} {path!r}: {exc}",
        details={"operation": operation},
    )


def _ensure_editable_doc(path: str) -> DocConverter:
    """Return the registered converter for *path* or reject with a 400."""
    converter = get_doc_converter(path)
    if converter is None:
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            f"unsupported editable document {path!r}",
        )
    return converter


def _agent_id_from_media_source(source: str) -> str | None:
    match = re.search(r"/agents/([A-Z0-9]+)/", source, re.IGNORECASE)
    return match.group(1) if match else None


def _workspace_io_path(path: str, *, from_workspace: bool = False) -> str:
    """Resolve an API path for ``BackendWorkspace``.

    ``file://`` is always a host absolute path.

    When ``from_workspace`` is true (workspace UI): leading ``/`` is relative to
    the agent workspace dir (``/logo.png`` → ``logo.png``).

    When false (default, chat/tool downloads): leading ``/`` is a host
    filesystem absolute (``/Users/…``, ``/root/…``). Paths without a leading
    ``/`` stay workspace-relative (``outbound/a.pptx``).
    """
    raw = path.strip()
    if raw.startswith("file://"):
        resolved = backend_workspace_path(raw)
        if resolved is None:
            raise OctopError(ErrorCode.NOT_FOUND, f"cannot resolve {path!r}")
        return resolved
    if from_workspace:
        return workspace_api_path(raw)
    if raw.startswith("/") or (len(raw) >= 2 and raw[1] == ":") or raw.startswith("\\\\"):
        return raw
    return workspace_api_path(raw)


_FROM_WORKSPACE_DESC = (
    "When true, leading '/' paths are workspace-relative (workspace UI). "
    "When false (default), leading '/' is host-absolute."
)


router = APIRouter()


@router.get("/agents/{agent_id}/workspace/tree")
async def list_tree(
    agent_id: str,
    path: str = "/",
    from_workspace: bool = Query(default=False, description=_FROM_WORKSPACE_DESC),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    """Single-level directory listing under ``path`` (agent must be running)."""
    ws = await require_running_workspace(
        agent_id, user=user, as_user=as_user, server=server, owner_only=True
    )
    io_path = _workspace_io_path(path, from_workspace=from_workspace)
    result = await ws.als(io_path)
    if result is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"cannot list {path!r}")
    entries = getattr(result, "entries", None) or []
    rows = [file_info_to_dict(f) for f in entries]
    if not is_host_absolute_path(io_path):
        for row in rows:
            row["path"] = reanchor_entry_path(str(row.get("path") or ""), parent=io_path)
    return rows


class WriteFileBody(BaseModel):
    content: str
    """UTF-8 text content. Use ``/upload`` for binary."""


class WriteDocBody(BaseModel):
    content: str
    """Markdown content to convert back into the document format."""


@router.get("/agents/{agent_id}/workspace/file")
async def read_file(
    agent_id: str,
    path: str,
    from_workspace: bool = Query(default=False, description=_FROM_WORKSPACE_DESC),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Read a UTF-8 text file."""
    ws = await require_agent_workspace(agent_id, user=user, as_user=as_user, server=server)
    content = await ws.aread_text(_workspace_io_path(path, from_workspace=from_workspace))
    if content is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"cannot read {path!r}")
    return {"path": path, "content": coerce_read_content(content)}


@router.put("/agents/{agent_id}/workspace/file")
async def write_file(
    agent_id: str,
    body: WriteFileBody,
    path: str,
    from_workspace: bool = Query(default=False, description=_FROM_WORKSPACE_DESC),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Overwrite ``path`` with ``body.content`` (text)."""
    ws = await require_running_workspace(
        agent_id, user=user, as_user=as_user, server=server, owner_only=True
    )
    # ★ 相位 A（文本相位）放在鉴权后：判据需要 ``ws.workspace_dir`` 才能把主机绝对 / `file://`
    # 拼写相对化后再套精确两形状（SEC-2：`file://` 不豁免）。响应体 ``path`` 仍用请求侧串。
    io_path = _assert_workspace_write_allowed(
        path, from_workspace=from_workspace, workspace_dir=ws.workspace_dir
    )
    # ★ 相位 B（解析相位）：判据与落盘同源，落盘用本行返回值（R11）。
    io_path = _assert_workspace_write_resolved(
        io_path, workspace_dir=ws.workspace_dir, resolve_ok=_host_resolve_enabled(ws)
    )
    converter = get_doc_converter(path)
    if converter is not None:
        # Editable-document paths are always stored as the binary document
        # format. This matters for workspace "new file": an empty .docx created
        # here must be a valid package so its preview (and edit round-trip)
        # works immediately instead of showing a 0-byte file.
        try:
            data = converter.from_markdown(body.content)
        except Exception as exc:
            raise OctopError(
                ErrorCode.SLASH_BAD_ARGS,
                f"cannot build document for {path!r}: {exc}",
            ) from exc
    else:
        data = body.content.encode("utf-8")
    try:
        await ws.aupload_bytes(io_path, data)
    except Exception as exc:
        raise OctopError(ErrorCode.NOT_FOUND, f"cannot write {path!r}: {exc}") from exc
    return {"path": path, "size": len(data)}


class MoveFileBody(BaseModel):
    destination: str
    """Workspace-relative destination path (e.g. ``/sub/file.txt``)."""


@router.post(
    "/agents/{agent_id}/workspace/mkdir",
    status_code=201,
    summary="Create workspace directory",
)
async def mkdir_workspace_dir(
    agent_id: str,
    path: str,
    from_workspace: bool = Query(
        default=True,
        description="Mutating endpoints always treat paths as workspace-relative.",
    ),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Create a directory (and parents) under the agent workspace."""
    _ = from_workspace  # API surface; mutations always use workspace-relative paths.
    rel = _assert_workspace_write_allowed(path, from_workspace=True)
    ws = await require_running_workspace(
        agent_id, user=user, as_user=as_user, server=server, owner_only=True
    )
    # ★ 相位 B（解析相位）· 范围①：落盘用本行返回值（R11），响应体 ``path`` 仍用请求侧。
    rel = _assert_workspace_write_resolved(
        rel, workspace_dir=ws.workspace_dir, resolve_ok=_host_resolve_enabled(ws)
    )
    try:
        await ws.amkdir(rel)
    except Exception as exc:
        raise _map_workspace_fs_error(exc, operation="mkdir", path=path) from exc
    api_path = path if path.startswith("/") else f"/{path}"
    return {"path": api_path, "is_dir": True}


@router.delete(
    "/agents/{agent_id}/workspace/file",
    status_code=204,
    summary="Delete workspace file or directory",
)
async def delete_workspace_file(
    agent_id: str,
    path: str,
    from_workspace: bool = Query(
        default=True,
        description="Mutating endpoints always treat paths as workspace-relative.",
    ),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Response:
    """Remove a file or directory tree from the agent workspace."""
    _ = from_workspace
    rel = _assert_workspace_write_allowed(path, from_workspace=True)
    ws = await require_running_workspace(
        agent_id, user=user, as_user=as_user, server=server, owner_only=True
    )
    # ★ 相位 B（解析相位）· 范围①：落盘用本行返回值（R11）。
    rel = _assert_workspace_write_resolved(
        rel, workspace_dir=ws.workspace_dir, resolve_ok=_host_resolve_enabled(ws)
    )
    try:
        await ws.adelete(rel)
    except Exception as exc:
        raise _map_workspace_fs_error(exc, operation="delete", path=path) from exc
    return Response(status_code=204)


@router.post(
    "/agents/{agent_id}/workspace/move",
    summary="Move or rename a workspace file or directory",
)
async def move_workspace_file(
    agent_id: str,
    body: MoveFileBody,
    path: str,
    from_workspace: bool = Query(
        default=True,
        description="Mutating endpoints always treat paths as workspace-relative.",
    ),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Move ``path`` to ``body.destination`` (rename when the parent directory is unchanged)."""
    _ = from_workspace
    src = _assert_workspace_write_allowed(path, from_workspace=True)
    dest = _assert_workspace_write_allowed(body.destination, from_workspace=True)
    ws = await require_running_workspace(
        agent_id, user=user, as_user=as_user, server=server, owner_only=True
    )
    # ★ 相位 B（解析相位）· 范围①：**两个值都解析**，落盘用解析后的 src/dest（R11）。
    resolve_ok = _host_resolve_enabled(ws)
    src = _assert_workspace_write_resolved(
        src, workspace_dir=ws.workspace_dir, resolve_ok=resolve_ok
    )
    dest = _assert_workspace_write_resolved(
        dest, workspace_dir=ws.workspace_dir, resolve_ok=resolve_ok
    )
    try:
        await ws.amove(src, dest)
    except Exception as exc:
        raise _map_workspace_fs_error(exc, operation="move", path=path) from exc
    dest_api = body.destination if body.destination.startswith("/") else f"/{body.destination}"
    return {"path": dest_api}


@router.post("/agents/{agent_id}/workspace/upload")
async def upload_file(
    agent_id: str,
    file: UploadFile = File(...),  # noqa: B008
    path: str | None = Query(default=None),
    from_workspace: bool = Query(default=False, description=_FROM_WORKSPACE_DESC),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Upload a binary file via multipart ``file=@...``."""
    ws = await require_running_workspace(
        agent_id, user=user, as_user=as_user, server=server, owner_only=True
    )
    target = path or f"/{file.filename or 'upload.bin'}"
    io_path = _assert_workspace_write_allowed(
        target, from_workspace=from_workspace, workspace_dir=ws.workspace_dir
    )
    # ★ 相位 B（解析相位）：落盘用本行返回值（R11）；响应体 ``path`` 仍用请求侧 ``target``。
    io_path = _assert_workspace_write_resolved(
        io_path, workspace_dir=ws.workspace_dir, resolve_ok=_host_resolve_enabled(ws)
    )
    data = await file.read()
    try:
        await ws.aupload_bytes(
            io_path,
            data,
        )
    except Exception as exc:
        raise OctopError(ErrorCode.NOT_FOUND, f"cannot upload to {target!r}: {exc}") from exc
    return {"path": target, "size": len(data)}


@router.get("/agents/{agent_id}/workspace/download")
async def download_file(
    agent_id: str,
    path: str,
    from_workspace: bool = Query(default=False, description=_FROM_WORKSPACE_DESC),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> StreamingResponse:
    """Stream ``path`` back as application/octet-stream.

    See ``from_workspace``: workspace UI uses true; chat/tool downloads use false.
    ``file://`` and other host-absolute paths are allowed for agent/OS tool
    outputs (Desktop, ``~/.octop/agents/…``, workspace tree) but denied for
    sensitive system roots (``/etc``, ``.harness-browser``, ``.octop-browser``, Windows system dirs).
    """
    ws = await require_agent_workspace(agent_id, user=user, as_user=as_user, server=server)
    io_path = _workspace_io_path(path, from_workspace=from_workspace)
    if is_host_absolute_path(io_path) and not is_allowed_host_download_abs_path(
        io_path,
        workspace=ws.workspace_dir,
    ):
        raise OctopError(ErrorCode.FORBIDDEN, f"cannot download {path!r}: path not allowed")

    try:
        file_blob = await ws.adownload_bytes(io_path)
    except PermissionError as exc:
        raise OctopError(ErrorCode.NOT_FOUND, f"cannot download {path!r}") from exc
    if file_blob is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"cannot download {path!r}") from None

    fname = io_path.rsplit("/", 1)[-1] or "download.bin"
    return StreamingResponse(
        iter([file_blob]),
        media_type="application/octet-stream",
        headers={"Content-Disposition": content_disposition(fname)},
    )


@router.get("/agents/{agent_id}/workspace/doc")
async def read_doc(
    agent_id: str,
    path: str,
    from_workspace: bool = Query(default=False, description=_FROM_WORKSPACE_DESC),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Read an editable document (e.g. ``.docx``) as Markdown for online editing."""
    converter = _ensure_editable_doc(path)
    ws = await require_agent_workspace(agent_id, user=user, as_user=as_user, server=server)
    io_path = _workspace_io_path(path, from_workspace=from_workspace)
    try:
        blob = await ws.adownload_bytes(io_path)
    except PermissionError as exc:
        raise OctopError(ErrorCode.NOT_FOUND, f"cannot read {path!r}") from exc
    if blob is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"cannot read {path!r}")
    try:
        content = converter.to_markdown(blob)
    except Exception as exc:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"cannot parse {path!r}: {exc}") from exc
    return {"path": path, "content": content}


@router.put("/agents/{agent_id}/workspace/doc")
async def write_doc(
    agent_id: str,
    body: WriteDocBody,
    path: str,
    from_workspace: bool = Query(
        default=True,
        description="Mutating endpoints always treat paths as workspace-relative.",
    ),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Convert Markdown *content* back to the document format and overwrite *path*."""
    _ = from_workspace  # Mutations always use workspace-relative paths.
    rel = _assert_workspace_write_allowed(path, from_workspace=True)
    converter = _ensure_editable_doc(path)
    ws = await require_running_workspace(agent_id, user=user, as_user=as_user, server=server)
    # ★ 相位 B（解析相位）· 范围①：落盘用本行返回值（R11），响应体 ``path`` 仍用请求侧。
    rel = _assert_workspace_write_resolved(
        rel, workspace_dir=ws.workspace_dir, resolve_ok=_host_resolve_enabled(ws)
    )
    try:
        data = converter.from_markdown(body.content)
    except Exception as exc:
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            f"cannot build document for {path!r}: {exc}",
        ) from exc
    try:
        await ws.aupload_bytes(rel, data)
    except Exception as exc:
        raise _map_workspace_fs_error(exc, operation="write", path=path) from exc
    return {"path": path, "size": len(data)}


@router.get(
    "/agents/{agent_id}/media/preview",
    summary="Preview image or video",
    response_class=StreamingResponse,
)
async def preview_media(
    agent_id: str,
    source: str = Query(..., description="``file://`` URL or workspace-relative path"),
    mime_type: str | None = Query(default=None, alias="mime_type"),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> StreamingResponse:
    """Stream an image or video inline for dashboard tool-result previews."""
    path_agent = _agent_id_from_media_source(source)
    effective_agent = path_agent or agent_id
    ws = await require_running_workspace(effective_agent, user=user, as_user=as_user, server=server)
    payload = await resolve_preview_payload(
        source=source,
        workspace=ws,
        mime_hint=mime_type or "",
    )
    if payload is None:
        raise OctopError(ErrorCode.NOT_FOUND, "preview not available for this source")
    data, mime = payload

    return StreamingResponse(
        iter([data]),
        media_type=mime,
        headers={"Content-Disposition": "inline"},
    )


@router.get("/agents/{agent_id}/workspace/glob")
async def glob_files(
    agent_id: str,
    pattern: str,
    path: str = "/",
    from_workspace: bool = Query(default=False, description=_FROM_WORKSPACE_DESC),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    ws = await require_running_workspace(
        agent_id, user=user, as_user=as_user, server=server, owner_only=True
    )
    root = _workspace_io_path(path, from_workspace=from_workspace)
    if pattern in ("**/*.md", "*.md") and root == ".":
        ls_result = await ws.als(".")
        if ls_result is None:
            raise OctopError(ErrorCode.NOT_FOUND, "glob failed")
        entries = getattr(ls_result, "entries", None) or []
        matches = []
        for f in entries:
            row = file_info_to_dict(f)
            if row.get("is_dir"):
                continue
            entry_path = str(row.get("path") or "")
            if entry_path.endswith(".md"):
                matches.append(row)
        return matches
    glob_result = await ws.aglob(pattern, root)
    if glob_result is None:
        raise OctopError(ErrorCode.NOT_FOUND, "glob failed")
    matches = getattr(glob_result, "matches", None) or []
    return [file_info_to_dict(item) for item in matches]


@router.get("/agents/{agent_id}/workspace/grep")
async def grep_files(
    agent_id: str,
    pattern: str,
    path: str = "/",
    from_workspace: bool = Query(default=False, description=_FROM_WORKSPACE_DESC),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    ws = await require_running_workspace(
        agent_id, user=user, as_user=as_user, server=server, owner_only=True
    )
    result = await ws.agrep(pattern, _workspace_io_path(path, from_workspace=from_workspace))
    if result is None:
        raise OctopError(ErrorCode.NOT_FOUND, "grep failed")
    matches = getattr(result, "matches", None) or []
    return [dict(m) for m in matches]


_MAX_WORKSPACE_ARCHIVE_BYTES = 200 * 1024 * 1024


@router.get(
    "/agents/{agent_id}/workspace/archive",
    summary="Download workspace as zip",
    response_class=StreamingResponse,
)
async def export_workspace_archive(
    agent_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> StreamingResponse:
    """Pack workspace files into a zip archive."""
    ws = await require_running_workspace(
        agent_id, user=user, as_user=as_user, server=server, owner_only=True
    )
    data = await export_workspace_zip(ws)
    filename = f"workspace-{agent_id}.zip"
    return StreamingResponse(
        iter([data]),
        media_type="application/zip",
        headers={"Content-Disposition": content_disposition(filename)},
    )


@router.post(
    "/agents/{agent_id}/workspace/archive",
    summary="Import workspace zip",
)
async def import_workspace_archive(
    agent_id: str,
    file: UploadFile = File(...),  # noqa: B008
    mode: Literal["merge", "replace"] = Query(default="merge"),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Import a zip archive into the workspace (merge or replace)."""
    raw = await file.read()
    if len(raw) > _MAX_WORKSPACE_ARCHIVE_BYTES:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "workspace archive too large (max 200MB)")
    if not raw:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "empty archive")

    ws = await require_running_workspace(
        agent_id, user=user, as_user=as_user, server=server, owner_only=True
    )
    local_ws = resolve_agent_workspace_dir(server, agent_id)
    result = await import_workspace_zip(
        ws,
        raw,
        mode=mode,
        local_workspace_dir=local_ws,
    )
    return {"ok": True, **result}
