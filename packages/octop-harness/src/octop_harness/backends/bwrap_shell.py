"""Bubblewrap directory jail for ``LocalShellBackend.execute``.

``root_dir`` is a backend mount (construction-time), not the agent workspace.
:class:`BubbledLocalShellBackend` is only constructed when
:func:`resolve_bubbled_bwrap` returns a path (Linux + ``virtual_mode`` +
non-host ``root_dir`` + ``bwrap``); then ``execute`` binds ``root_dir`` at
jail ``/`` so agent-facing absolute paths match deepagents ``virtual_mode``
file tools.

Host execute without a jail lives in :mod:`octop_harness.backends.local_shell`.
This module re-exports that backend so existing imports keep working.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from deepagents.backends.protocol import ExecuteResponse

from octop_harness.backends.local_shell import (
    HarnessLocalShellBackend,
    format_execute_result,
    is_host_root,
    map_virtual_abs_path,
    map_virtual_paths_in_env,
    present_host_paths_in_output,
    rewrite_virtual_paths_in_command,
)

logger = logging.getLogger(__name__)

_RO_BINDS = ("/usr", "/bin", "/lib", "/lib64")
_ETC_TRY = (
    "/etc/resolv.conf",
    "/etc/passwd",
    "/etc/group",
    "/etc/nsswitch.conf",
)


def resolve_bubbled_bwrap(
    *,
    virtual_mode: bool,
    root_dir: Path | str,
    platform: str | None = None,
    bwrap_path: str | bool | None = False,
) -> str | None:
    """Return ``bwrap`` path when :class:`BubbledLocalShellBackend` should be used.

    Requires Linux, ``virtual_mode``, a non-host ``root_dir``, and ``bwrap``.
    Pass ``bwrap_path`` to skip ``shutil.which`` (``False`` = probe, ``None`` = missing).
    """
    if (platform if platform is not None else sys.platform) != "linux":
        return None
    if not virtual_mode or is_host_root(root_dir):
        return None
    if bwrap_path is False:
        return shutil.which("bwrap")
    return bwrap_path if isinstance(bwrap_path, str) else None


def can_use_bubbled_shell(
    *,
    virtual_mode: bool,
    root_dir: Path | str,
    platform: str | None = None,
    bwrap_path: str | bool | None = False,
) -> bool:
    """Return True when :class:`BubbledLocalShellBackend` should be constructed."""
    return (
        resolve_bubbled_bwrap(
            virtual_mode=virtual_mode,
            root_dir=root_dir,
            platform=platform,
            bwrap_path=bwrap_path,
        )
        is not None
    )


def build_bwrap_argv(
    *,
    bwrap: str,
    root_dir: Path,
    command: str,
    work_dir: str = "/",
    extra_binds: list[tuple[str, str]] | None = None,
) -> list[str]:
    """Assemble ``bwrap`` argv; outer ``subprocess`` must use ``shell=False``."""
    root = root_dir.expanduser().resolve()
    argv: list[str] = [
        bwrap,
        "--die-with-parent",
        "--new-session",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--bind",
        str(root),
        "/",
    ]
    for host_path in _RO_BINDS:
        if Path(host_path).exists():
            argv.extend(["--ro-bind", host_path, host_path])
    for etc in _ETC_TRY:
        argv.extend(["--ro-bind-try", etc, etc])
    if extra_binds:
        for src, dst in extra_binds:
            argv.extend(["--bind", src, dst])
    argv.extend(
        [
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--tmpfs",
            "/tmp",
            "--chdir",
            work_dir,
            "--",
            "/bin/sh",
            "-c",
            command,
        ]
    )
    return argv


class BubbledLocalShellBackend(HarnessLocalShellBackend):
    """``LocalShellBackend`` whose ``execute`` runs under a bubblewrap rootfs jail.

    Construct only when :func:`resolve_bubbled_bwrap` returns a path; pass that
    path as ``bwrap_path``. File tools still use deepagents ``virtual_mode``
    path join; only ``execute`` is process-isolated.
    """

    def __init__(
        self,
        root_dir: str | Path | None = None,
        *,
        bwrap_path: str,
        workspace_dir: str | Path | None = None,
        virtual_mode: bool | None = None,
        env: dict[str, str] | None = None,
        inherit_env: bool = True,
        system_files_path: str = "",
        **kwargs: Any,
    ) -> None:
        from octop_harness.backends.workspace import normalize_system_files_path

        super().__init__(
            root_dir=root_dir,
            workspace_dir=workspace_dir,
            virtual_mode=virtual_mode,
            env=env,
            inherit_env=inherit_env,
            **kwargs,
        )
        self._bwrap_path: str | None = bwrap_path
        self._system_files_path = normalize_system_files_path(system_files_path)

    def _skill_extra_binds(self) -> list[tuple[str, str]]:
        if self._workspace_dir is None:
            return []
        cwd = getattr(self, "cwd", None)
        if cwd is None:
            return []
        if self._workspace_dir.resolve() == Path(cwd).resolve():
            return []
        binds: list[tuple[str, str]] = []
        for name, dest in (("skills", "/skills"), ("_builtin_skills", "/_builtin_skills")):
            candidates: list[Path] = []
            if self._system_files_path:
                candidates.append(self._workspace_dir / self._system_files_path / name)
            legacy = self._workspace_dir / name
            if legacy not in candidates:
                candidates.append(legacy)
            src = next((path for path in candidates if path.is_dir()), None)
            if src is not None:
                binds.append((str(src), dest))
        return binds

    def _virtual_workspace_cwd(self) -> str:
        if self._workspace_dir is None:
            return "/"
        try:
            relative = self._workspace_dir.relative_to(Path(self.cwd).resolve())
        except ValueError:
            return "/"
        text = relative.as_posix()
        return "/" if text in {"", "."} else f"/{text}"

    def _execute_in_bwrap(
        self,
        command: str,
        *,
        bwrap: str,
        timeout: int | None,
    ) -> ExecuteResponse:
        effective_timeout = timeout if timeout is not None else self._default_timeout
        if effective_timeout <= 0:
            return ExecuteResponse(
                output=f"Error: timeout must be positive, got {effective_timeout}",
                exit_code=1,
                truncated=False,
            )

        argv = build_bwrap_argv(
            bwrap=bwrap,
            root_dir=self.cwd,
            command=command,
            work_dir=self._virtual_workspace_cwd(),
            extra_binds=self._skill_extra_binds(),
        )
        try:
            result = subprocess.run(
                argv,
                check=False,
                shell=False,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                text=True,
                timeout=effective_timeout,
                env=self._env,
            )
            return format_execute_result(result, max_output_bytes=self._max_output_bytes)
        except FileNotFoundError as exc:
            self._bwrap_path = None
            logger.warning(
                "bwrap failed to start (%s); falling back to translated host execute",
                exc,
            )
            return super().execute(command, timeout=timeout)
        except subprocess.TimeoutExpired:
            if timeout is not None:
                msg = (
                    f"Error: Command timed out after {effective_timeout} seconds "
                    "(custom timeout). The command may be stuck or require more time."
                )
            else:
                msg = (
                    f"Error: Command timed out after {effective_timeout} seconds. "
                    "For long-running commands, re-run using the timeout parameter."
                )
            return ExecuteResponse(
                output=msg,
                exit_code=124,
                truncated=False,
            )
        except Exception as exc:  # sandbox boundary: any failure becomes a tool error; pylint: disable=broad-except
            return ExecuteResponse(
                output=f"Error executing command ({type(exc).__name__}): {exc}",
                exit_code=1,
                truncated=False,
            )

    def execute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        if not command or not isinstance(command, str):
            return super().execute(command, timeout=timeout)

        self._refresh_execute_env()

        bwrap = self._bwrap_path
        if bwrap is None:
            return super().execute(command, timeout=timeout)

        return self._execute_in_bwrap(command, bwrap=bwrap, timeout=timeout)


__all__ = [
    "BubbledLocalShellBackend",
    "HarnessLocalShellBackend",
    "build_bwrap_argv",
    "can_use_bubbled_shell",
    "is_host_root",
    "map_virtual_abs_path",
    "map_virtual_paths_in_env",
    "present_host_paths_in_output",
    "resolve_bubbled_bwrap",
    "rewrite_virtual_paths_in_command",
]
