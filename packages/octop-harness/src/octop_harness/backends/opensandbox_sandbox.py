"""OpenSandbox remote backend (optional ``[opensandbox]`` extra).

Creates a remote sandbox on construct and destroys it on :meth:`close`.
Implements the three Deep Agents ``BaseSandbox`` primitives so file tools and
``execute`` run inside OpenSandbox.

Requires ``opensandbox>=0.1.16``. Install with::

    pip install 'octop-harness[opensandbox]'
"""

from __future__ import annotations

import contextlib
import logging
import shlex
from datetime import timedelta
from typing import Any

from deepagents.backends.protocol import (
    FILE_NOT_FOUND,
    INVALID_PATH,
    IS_DIRECTORY,
    PERMISSION_DENIED,
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox

logger = logging.getLogger(__name__)

_DEFAULT_IMAGE = "python:3.12"
_DEFAULT_TIMEOUT = 30 * 60
_DEFAULT_FILE_MODE = 0o644

_MISSING = (
    "OpenSandbox backend requires the optional dependency 'opensandbox'. "
    "Install with: pip install 'octop-harness[opensandbox]'."
)


def _import_opensandbox() -> Any:
    try:
        import opensandbox
    except ImportError as exc:
        raise ImportError(_MISSING) from exc
    return opensandbox


def _connection_config(
    *,
    api_key: str | None,
    domain: str | None,
    protocol: str,
    use_server_proxy: bool,
) -> Any:
    """Build a sync connection config (import path varies slightly by SDK version)."""
    kwargs: dict[str, Any] = {}
    if api_key:
        kwargs["api_key"] = api_key
    if domain:
        kwargs["domain"] = domain
    if protocol:
        kwargs["protocol"] = protocol
    if use_server_proxy:
        kwargs["use_server_proxy"] = True
    try:
        from opensandbox.config.connection_sync import ConnectionConfigSync

        return ConnectionConfigSync(**kwargs)
    except ImportError:
        pass
    try:
        from opensandbox.config import ConnectionConfigSync

        return ConnectionConfigSync(**kwargs)
    except ImportError:
        from opensandbox.config import ConnectionConfig

        return ConnectionConfig(**kwargs)


class OpenSandbox(BaseSandbox):
    """Remote OpenSandbox implementing :class:`BaseSandbox`.

    Construct via ``resolve_backend({"type": "opensandbox", ...})``.
    :meth:`close` destroys the remote sandbox (agent-runtime lifecycle).
    """

    def __init__(
        self,
        *,
        image: str = _DEFAULT_IMAGE,
        api_key: str | None = None,
        domain: str | None = None,
        protocol: str = "http",
        timeout: int = _DEFAULT_TIMEOUT,
        command_timeout: int | None = None,
        use_server_proxy: bool = False,
        sandbox: Any | None = None,
        **_ignored: Any,
    ) -> None:
        _import_opensandbox()
        from opensandbox import SandboxSync

        self.sandbox_fs: bool = True
        self.virtual_mode: bool = True
        self._closed = False
        self._default_timeout = int(command_timeout if command_timeout is not None else timeout)
        self._sandbox: Any
        if sandbox is not None:
            self._sandbox = sandbox
            return

        connection = _connection_config(
            api_key=api_key,
            domain=domain,
            protocol=protocol or "http",
            use_server_proxy=use_server_proxy,
        )
        create_kwargs: dict[str, Any] = {"connection_config": connection}
        idle = int(timeout)
        if idle > 0:
            create_kwargs["timeout"] = timedelta(seconds=idle)
        self._sandbox = SandboxSync.create(str(image or _DEFAULT_IMAGE), **create_kwargs)
        logger.info("OpenSandbox ready id=%s image=%s domain=%s", self.id, image, domain)

    @property
    def id(self) -> str:
        sid = getattr(self._sandbox, "id", None) or getattr(self._sandbox, "sandbox_id", None)
        return str(sid or "")

    def execute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        effective = timeout if timeout is not None else self._default_timeout
        opts = None
        try:
            from opensandbox.models.execd import RunCommandOpts

            opts = RunCommandOpts(
                timeout=timedelta(seconds=effective) if effective else None,
            )
        except ImportError:
            opts = None
        if opts is not None:
            execution = self._sandbox.commands.run(command, opts=opts)
        else:
            execution = self._sandbox.commands.run(command)

        stdout_parts = getattr(getattr(execution, "logs", None), "stdout", None) or []
        stderr_parts = getattr(getattr(execution, "logs", None), "stderr", None) or []
        stdout = "\n".join(getattr(msg, "text", str(msg)) for msg in stdout_parts)
        stderr = "\n".join(getattr(msg, "text", str(msg)) for msg in stderr_parts)
        if not stdout and not stderr:
            stdout = str(getattr(execution, "stdout", "") or "")
            stderr = str(getattr(execution, "stderr", "") or "")
        output = stdout
        if stderr.strip():
            output = f"{output}\n{stderr}" if output else stderr
        return ExecuteResponse(
            output=output,
            exit_code=int(getattr(execution, "exit_code", 0) or 0),
            truncated=False,
        )

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        from opensandbox.models.filesystem import WriteEntry

        responses: list[FileUploadResponse] = [FileUploadResponse(path=path, error=None) for path, _ in files]
        entries: list[Any] = []
        valid_indices: list[int] = []
        for i, (path, content) in enumerate(files):
            if not path.startswith("/"):
                responses[i] = FileUploadResponse(path=path, error=INVALID_PATH)
                continue
            entries.append(WriteEntry(path=path, data=content, mode=_DEFAULT_FILE_MODE))
            valid_indices.append(i)
        if not entries:
            return responses
        try:
            self._sandbox.files.write_files(entries)
        except Exception as exc:  # SDK error types vary; every entry fails together; pylint: disable=broad-except
            for i in valid_indices:
                responses[i] = FileUploadResponse(path=files[i][0], error=str(exc))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses: list[FileDownloadResponse] = []
        reader = getattr(self._sandbox.files, "read_bytes", None)
        text_reader = getattr(self._sandbox.files, "read_file", None)
        for path in paths:
            if not path.startswith("/"):
                responses.append(FileDownloadResponse(path=path, content=None, error=INVALID_PATH))
                continue
            try:
                if callable(reader):
                    content = reader(path)
                elif callable(text_reader):
                    raw = text_reader(path)
                    content = raw if isinstance(raw, bytes) else str(raw).encode("utf-8")
                else:
                    raise RuntimeError("OpenSandbox SDK has no file read method")
            except Exception as exc:  # SDK error types vary; report per path; pylint: disable=broad-except
                responses.append(
                    FileDownloadResponse(
                        path=path,
                        content=None,
                        error=self._classify_read_error(path, exc),
                    )
                )
            else:
                responses.append(FileDownloadResponse(path=path, content=content, error=None))
        return responses

    def _classify_read_error(self, path: str, exc: Exception) -> str:
        quoted = shlex.quote(path)
        probe = self.execute(
            f"if [ -d {quoted} ]; then echo DIR; "
            f"elif [ ! -e {quoted} ]; then echo MISSING; "
            f"elif [ ! -r {quoted} ]; then echo NOREAD; "
            f"else echo OTHER; fi"
        )
        marker = (probe.output or "").strip()
        if marker == "DIR":
            return IS_DIRECTORY
        if marker == "MISSING":
            return FILE_NOT_FOUND
        if marker == "NOREAD":
            return PERMISSION_DENIED
        message = str(exc)
        if "FILE_NOT_FOUND" in message or "no such file" in message.lower():
            return FILE_NOT_FOUND
        return message

    def close(self) -> None:
        """Destroy the remote sandbox (idempotent)."""
        if self._closed:
            return
        self._closed = True
        sandbox = self._sandbox
        destroy = getattr(sandbox, "destroy", None)
        if callable(destroy):
            with contextlib.suppress(Exception):
                destroy()
            return
        kill = getattr(sandbox, "kill", None)
        if callable(kill):
            with contextlib.suppress(Exception):
                kill()
        closer = getattr(sandbox, "close", None)
        if callable(closer):
            with contextlib.suppress(Exception):
                closer()

    def destroy(self) -> None:
        self.close()

    def __enter__(self) -> OpenSandbox:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
