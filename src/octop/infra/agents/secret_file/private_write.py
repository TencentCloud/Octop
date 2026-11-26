"""Private write primitive for secret files.

Guarantees (POSIX local backends): the auth directory is ``0700``, the file is
``0600`` owned by the Octop process user, writes are atomic (temp file +
``os.replace``) and a failed write never clobbers the previous file. Symlink
path components and symlink targets are rejected so a hostile or stale link
cannot redirect the write outside the auth directory.

Backends that cannot honour these guarantees are refused outright — no
degraded write:

* cloud object storage (COS/S3/OSS/OBS/Postgres) has no POSIX mode semantics;
* sandbox backends (``sandbox_fs``, Docker / OpenSandbox) upload via tar
  archives with a hard-coded 0644 mode and their ``execute`` has no stdin, so
  a private-at-creation, atomically-finalized write cannot be guaranteed
  without leaking the secret into exec logs;
* scoped local jails without a host-visible workspace directory cannot be
  verified from the host.
* non-POSIX hosts have no verified private ACL implementation.
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
from pathlib import Path
from typing import TYPE_CHECKING

from octop_harness.backends.workspace import is_cloud_storage_backend

from octop.infra.errors import ErrorCode, OctopError

if TYPE_CHECKING:
    from octop_harness.backends.workspace import BackendWorkspace

logger = logging.getLogger(__name__)

_POSIX = os.name == "posix"
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def _unsupported(detail: str) -> OctopError:
    return OctopError(
        ErrorCode.SECRET_BACKEND_UNSUPPORTED,
        f"this workspace backend cannot store credential files privately ({detail})",
    )


def _write_failed(detail: str) -> OctopError:
    # *detail* must describe the operation, never the secret content.
    return OctopError(
        ErrorCode.SECRET_WRITE_FAILED,
        f"failed to store the credential file ({detail})",
    )


# ---------------------------------------------------------------------------
# Local host filesystem
# ---------------------------------------------------------------------------


def _assert_no_symlink(auth_dir: Path, name: str) -> None:
    """Reject when the auth dir or any existing component of *name* is a symlink."""
    if auth_dir.is_symlink():
        raise OctopError(
            ErrorCode.SECRET_PATH_INVALID,
            "auth directory must not be a symlink",
        )
    current = auth_dir
    for segment in name.split("/"):
        current = current / segment
        if current.is_symlink():
            raise OctopError(
                ErrorCode.SECRET_PATH_INVALID,
                "secret path must not traverse symlinks",
            )


def _ensure_private_dir(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if _POSIX:
        os.chmod(path, 0o700)


def _write_local(auth_dir: Path, name: str, data: bytes) -> Path:
    # Symlink checks come before any mkdir/chmod so a hostile link never gets
    # its target directory's permissions rewritten.
    if auth_dir.is_symlink():
        raise OctopError(
            ErrorCode.SECRET_PATH_INVALID,
            "auth directory must not be a symlink",
        )
    if _POSIX and auth_dir.exists():
        stat = auth_dir.stat()
        if stat.st_uid != os.geteuid():
            raise _unsupported("auth directory is owned by a different user")
    _assert_no_symlink(auth_dir, name)
    _ensure_private_dir(auth_dir)
    target = auth_dir / name
    try:
        target.resolve(strict=False).relative_to(auth_dir.resolve())
    except ValueError:
        raise OctopError(
            ErrorCode.SECRET_PATH_INVALID,
            "secret path escapes the auth directory",
        ) from None
    parent = auth_dir
    for segment in name.split("/")[:-1]:
        parent = parent / segment
        _ensure_private_dir(parent)
    tmp = parent / f".{target.name}.tmp-{secrets.token_hex(4)}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW
    try:
        fd = os.open(tmp, flags, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                os.fchmod(handle.fileno(), 0o600)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        os.replace(tmp, target)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        # Never include path payloads that could echo the secret; errno only.
        raise _write_failed(f"local write error {exc.errno}") from None
    return target


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def secret_backend_supported(backend: object) -> bool:
    """Whether the backend can honour the private-write guarantees."""
    if not _POSIX or getattr(backend, "sandbox_fs", False):
        return False
    return not is_cloud_storage_backend(backend)


async def write_secret_private(
    workspace: BackendWorkspace,
    *,
    fragment: str,
    content: str,
) -> None:
    """Write *content* as a private file at the workspace-relative *fragment*.

    Raises :class:`OctopError` (``SECRET_BACKEND_UNSUPPORTED`` /
    ``SECRET_WRITE_FAILED`` / ``SECRET_PATH_INVALID``) on failure; the previous
    file, if any, is left untouched.
    """
    if not _POSIX:
        raise _unsupported("non-POSIX hosts have no verified private ACL support")
    backend = workspace.backend
    if getattr(backend, "sandbox_fs", False):
        raise _unsupported("sandbox backends cannot guarantee private atomic writes")
    if is_cloud_storage_backend(backend):
        raise _unsupported("cloud object storage has no private POSIX semantics")
    root = Path(workspace.workspace_dir)
    if not root.is_dir():
        raise _unsupported("workspace is not a host-local directory")
    resolved = Path(workspace.resolve_path(fragment))
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        raise _unsupported("workspace path is not host-local") from None
    data = content.encode("utf-8")
    await asyncio.to_thread(_write_local_sync, root, fragment, data)


def _write_local_sync(root: Path, fragment: str, data: bytes) -> None:
    # ``fragment`` is ``{auth_fragment}/{name}``; the auth root is
    # ``.octop/auth`` (two segments) or ``.octop-auth`` (one segment).
    parts = Path(fragment).parts
    if len(parts) >= 2 and parts[0] == ".octop":
        auth_root = root / parts[0] / parts[1]
        name = "/".join(parts[2:])
    else:
        auth_root = root / parts[0]
        name = "/".join(parts[1:])
    if not name:
        raise OctopError(ErrorCode.SECRET_PATH_INVALID, "secret path names a directory")
    _assert_no_symlink(root, auth_root.relative_to(root).as_posix())
    _write_local(auth_root, name, data)


__all__ = ["secret_backend_supported", "write_secret_private"]
