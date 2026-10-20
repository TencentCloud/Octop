"""Docker-backed sandbox for agent file I/O and execute.

**Same path, two places (no bind-mount):**

- Host ``workspace_dir``: set by the host when the agent is created/started
  (Octop default is ``{OCTOP_HOME}/agents/<id>/``, but it is whatever value the
  host passes — not a hardcoded constant). Used for sessions / memory /
  checkpoints on the host filesystem.
- In-container workspace root: by default the **same absolute path string** as
  ``workspace_dir``, created inside the sandbox. Agent-visible files
  (``SOUL.md``, skills, tool writes) live there. Explicit ``workspace_path``
  overrides; without either path the fallback is ``/workspace``.

``ls`` / ``read`` / ``write`` / ``execute`` all run in the container via the
Docker Python SDK (``exec_run``, ``put_archive``, ``get_archive``). Host and
sandbox trees are **not** automatically bind-mounted to each other.

**Sandbox naming** (``sandbox_scope`` + ``sandbox_prefix``, default prefix
``sandbox``; Octop may pass ``octop_sandbox``):

- ``agent`` (default): ``{prefix}_agent_{agent_id}``
- ``user``: ``{prefix}_{username}`` (multi-expert share one sandbox)
- ``fixed``: ``sandbox_id`` as given

Missing containers are created; ``close()`` / deleting an expert does **not**
remove the container. Explicit :meth:`destroy` stops and removes it — workspace
files in the container FS are deleted with the container (no named volumes).
Optional ``volumes`` are passed through unchanged for user-configured mounts.

Requires the optional ``[docker]`` extra (``pip install
'octop-harness[docker]'``).
"""

from __future__ import annotations

import asyncio
import atexit
import contextlib
import io
import logging
import re
import shlex
import tarfile
import threading
import time
import weakref
from pathlib import Path, PurePosixPath
from typing import Any, Final, Literal

from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox

from octop_harness.runtime_env import load_dotenv_path, parse_env_text, resolve_docker_execute_env

logger = logging.getLogger(__name__)

_DEFAULT_WORKSPACE_PATH: Final[str] = "/workspace"
_DEFAULT_IMAGE: Final[str] = "python:3.12-slim"
_DEFAULT_TIMEOUT: Final[int] = 120
_DEFAULT_MAX_OUTPUT: Final[int] = 100_000
_DEFAULT_SANDBOX_PREFIX: Final[str] = "sandbox"
_LABEL_SANDBOX: Final[str] = "harness.agent.sandbox"
_LABEL_AGENT_ID: Final[str] = "harness.agent.id"
_LABEL_SCOPE: Final[str] = "harness.agent.sandbox_scope"

SandboxScope = Literal["agent", "user", "fixed"]

_MISSING_DOCKER = (
    "Docker sandbox backend requires the optional dependency 'docker'. "
    "Install with: pip install 'octop-harness[docker]'."
)

_live_sandboxes: weakref.WeakSet[Any] = weakref.WeakSet()
_atexit_state: dict[str, bool] = {"registered": False}
_atexit_lock = threading.Lock()


def _register_atexit() -> None:
    with _atexit_lock:
        if _atexit_state["registered"]:
            return
        atexit.register(_cleanup_all_sandboxes)
        _atexit_state["registered"] = True


def _cleanup_all_sandboxes() -> None:
    """Detach Python wrappers only — never stop/remove persistent containers."""
    for sandbox in list(_live_sandboxes):
        with contextlib.suppress(Exception):  # pragma: no cover - best-effort
            sandbox._detach()


def _import_docker() -> Any:
    try:
        import docker
    except ImportError as exc:
        raise ImportError(_MISSING_DOCKER) from exc
    return docker


def _is_credstore_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "credential" in msg or "credsstore" in msg or "credstore" in msg


def _pull_anonymous(client: Any, image: str) -> None:
    """Pull *image* without consulting the Docker credential helper.

    Public images (e.g. ``python:3.12-slim``) do not need auth. Passing an
    empty ``auth_config`` skips ``credsStore`` resolution, which otherwise
    fails when ``docker-credential-osxkeychain`` is missing from PATH (common
    when the host process was not launched via Docker Desktop).
    """
    stream = client.api.pull(image, stream=True, decode=True, auth_config={})
    for chunk in stream:
        if not isinstance(chunk, dict):
            continue
        err = chunk.get("error") or chunk.get("errorDetail")
        if err:
            if isinstance(err, dict):
                err = err.get("message") or str(err)
            raise RuntimeError(str(err))


def ensure_docker_image(image: str, *, client: Any | None = None) -> bool:
    """Ensure *image* is present locally; pull if missing.

    Returns ``True`` if a pull was performed, ``False`` if the image was
    already local.

    ``containers.run`` auto-pulls on miss, but credential-helper failures
    (common on macOS without Docker Desktop's helper in PATH) become opaque
    ``DockerException``s. We pull explicitly; on credstore errors we retry
    an anonymous pull (sufficient for public images) before raising a clear
    :class:`RuntimeError`.
    """
    docker_mod = _import_docker()
    docker_client = client if client is not None else docker_mod.from_env()
    try:
        docker_client.images.get(image)
        return False
    except docker_mod.errors.ImageNotFound:
        pass

    logger.info("Pulling docker image %s", image)
    try:
        docker_client.images.pull(image)
        return True
    except Exception as first_exc:  # report any pull failure to the caller; pylint: disable=broad-except
        if not _is_credstore_error(first_exc):
            raise RuntimeError(
                f"Docker image {image!r} is not available locally and pull failed "
                f"({first_exc}). Fix credentials / network, or run: docker pull {image}"
            ) from first_exc

        logger.warning(
            "Docker credential helper failed for %s (%s); retrying anonymous pull",
            image,
            first_exc,
        )
        try:
            _pull_anonymous(docker_client, image)
            return True
        except Exception as second_exc:
            raise RuntimeError(
                f"Docker image {image!r} is not available locally. "
                f"Credential helper failed ({first_exc}); anonymous pull also failed "
                f"({second_exc}). Add docker-credential-* to PATH "
                f"(e.g. /Applications/Docker.app/Contents/Resources/bin), "
                f"or run: docker pull {image}"
            ) from second_exc


def _normalize_container_path(path: str) -> str:
    """Collapse ``.`` / ``..`` in a container absolute path (posix)."""
    parts: list[str] = []
    for part in PurePosixPath(path).parts:
        if part in ("/", ""):
            continue
        if part == ".":
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/" + "/".join(parts) if parts else "/"


def _sanitize_container_name(raw: str) -> str:
    """Docker container names: ``[a-zA-Z0-9][a-zA-Z0-9_.-]*`` (max ~200)."""
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", raw).strip("-._")
    if not cleaned:
        cleaned = "sandbox"
    if not cleaned[0].isalnum():
        cleaned = f"h{cleaned}"
    return cleaned[:200]


def resolve_sandbox_name(
    *,
    sandbox_scope: str = "agent",
    sandbox_prefix: str = _DEFAULT_SANDBOX_PREFIX,
    agent_id: str | None = None,
    username: str | None = None,
    sandbox_id: str | None = None,
    container_name: str | None = None,
) -> str | None:
    """Resolve the Docker container name for a sandbox, or ``None`` if ephemeral.

    Explicit ``container_name`` wins. Otherwise:

    - ``agent`` → ``{prefix}_agent_{agent_id}``
    - ``user`` → ``{prefix}_{username}`` (requires ``username``)
    - ``fixed`` → ``sandbox_id`` (requires ``sandbox_id``)
    """
    if container_name and str(container_name).strip():
        return _sanitize_container_name(str(container_name).strip())

    scope = (sandbox_scope or "agent").strip().lower()
    prefix = (sandbox_prefix or _DEFAULT_SANDBOX_PREFIX).strip() or _DEFAULT_SANDBOX_PREFIX
    prefix = _sanitize_container_name(prefix)

    if scope == "fixed":
        if not sandbox_id or not str(sandbox_id).strip():
            raise ValueError("sandbox_scope='fixed' requires sandbox_id")
        return _sanitize_container_name(str(sandbox_id).strip())

    if scope == "user":
        if not username or not str(username).strip():
            raise ValueError("sandbox_scope='user' requires username")
        return _sanitize_container_name(f"{prefix}_{str(username).strip()}")

    if scope != "agent":
        raise ValueError(f"Unknown sandbox_scope {sandbox_scope!r}; expected 'agent', 'user', or 'fixed'")

    if agent_id and str(agent_id).strip():
        return _sanitize_container_name(f"{prefix}_agent_{str(agent_id).strip()}")
    return None


def resolve_container_name(
    *,
    container_name: str | None = None,
    agent_id: str | None = None,
    sandbox_scope: str = "agent",
    sandbox_prefix: str = _DEFAULT_SANDBOX_PREFIX,
    username: str | None = None,
    sandbox_id: str | None = None,
) -> str | None:
    """Alias for :func:`resolve_sandbox_name` (backward-compatible name)."""
    return resolve_sandbox_name(
        sandbox_scope=sandbox_scope,
        sandbox_prefix=sandbox_prefix,
        agent_id=agent_id,
        username=username,
        sandbox_id=sandbox_id,
        container_name=container_name,
    )


def _in_container_workspace_root(
    workspace_path: str | None,
    workspace_dir: str | Path | None,
) -> str:
    """Resolve the sandbox workspace directory path (exists only inside the container).

    Precedence: explicit ``workspace_path`` → absolute ``workspace_dir`` (same
    string as the host runtime dir, e.g. ``~/.octop/agents/<id>/``) → ``/workspace``.
    """
    if workspace_path is not None and str(workspace_path).strip():
        root = str(workspace_path).strip().replace("\\", "/")
    elif workspace_dir is not None:
        root = str(Path(workspace_dir).expanduser().resolve()).replace("\\", "/")
    else:
        root = _DEFAULT_WORKSPACE_PATH
    if not root.startswith("/"):
        root = f"/{root}"
    return _normalize_container_path(root.rstrip("/") or _DEFAULT_WORKSPACE_PATH)


class DockerSandbox(BaseSandbox):
    """Docker sandbox implementing :class:`BaseSandbox`.

    Construct via ``resolve_backend({"type": "docker", ...}, workspace_dir=...)``
    or directly. Call :meth:`close` to detach the Python wrapper without
    removing the container; call :meth:`destroy` to stop and remove it
    (container workspace files are deleted with the container).

    By default the in-container workspace root mirrors ``workspace_dir``'s
    absolute path (agent files in the sandbox; sessions/memory on the host at
    the same path). Set ``workspace_path`` to override.
    """

    def __init__(
        self,
        *,
        workspace_dir: str | Path | None = None,
        workspace_path: str | None = None,
        image: str = _DEFAULT_IMAGE,
        allow_network: bool = False,
        memory: str | None = "512m",
        cpus: float | None = 1.0,
        pids_limit: int | None = 256,
        command_timeout: int = _DEFAULT_TIMEOUT,
        max_output_bytes: int = _DEFAULT_MAX_OUTPUT,
        auto_remove: bool | None = None,
        volumes: dict[str, Any] | list[str] | None = None,
        extra_run_args: list[str] | None = None,
        environment: dict[str, str] | None = None,
        environment_file: str | Path | None = None,
        client: Any | None = None,
        agent_id: str | None = None,
        container_name: str | None = None,
        sandbox_scope: str = "agent",
        sandbox_prefix: str = _DEFAULT_SANDBOX_PREFIX,
        username: str | None = None,
        sandbox_id: str | None = None,
        previewable: bool | None = None,
        system_files_path: str = "",
        **_ignored: Any,
    ) -> None:
        docker = _import_docker()
        self._docker = docker
        self._client = client if client is not None else docker.from_env()

        # Host workspace_dir: runtime persistence only. Same path string is used
        # in-container as the agent workspace root unless workspace_path is set.
        self._host_workspace_dir = Path(workspace_dir).expanduser().resolve() if workspace_dir is not None else None
        self._workspace_root = _in_container_workspace_root(workspace_path, workspace_dir)
        prefix = str(system_files_path or "").strip().replace("\\", "/").strip("/")
        self._system_files_path = prefix if prefix not in {".", ".."} and ".." not in prefix.split("/") else ""

        # Duck-typed by BackendWorkspace: sandbox FS, no host mount.
        self.sandbox_fs: bool = True
        self.virtual_mode: bool = True

        self._image = image
        self._allow_network = allow_network
        self._command_timeout = max(1, int(command_timeout))
        self._max_output_bytes = max_output_bytes
        self._agent_id = (str(agent_id).strip() if agent_id else "") or None
        self._username = (str(username).strip() if username else "") or None
        self._sandbox_id = (str(sandbox_id).strip() if sandbox_id else "") or None
        self._sandbox_scope = (sandbox_scope or "agent").strip().lower()
        self._sandbox_prefix = (sandbox_prefix or _DEFAULT_SANDBOX_PREFIX).strip() or _DEFAULT_SANDBOX_PREFIX
        self._container_name = resolve_sandbox_name(
            sandbox_scope=self._sandbox_scope,
            sandbox_prefix=self._sandbox_prefix,
            agent_id=self._agent_id,
            username=self._username,
            sandbox_id=self._sandbox_id,
            container_name=container_name,
        )
        if previewable is None:
            self.previewable = self._sandbox_scope == "fixed"
        else:
            self.previewable = bool(previewable)
        # Named sandboxes persist; ephemeral (probe/browse) auto-clean on close.
        self._auto_remove = bool(auto_remove) if auto_remove is not None else self._container_name is None
        self._closed = False
        self._lock = threading.RLock()
        self._volumes = volumes
        self._memory = memory
        self._cpus = cpus
        self._pids_limit = pids_limit
        self._environment = {str(k): str(v) for k, v in dict(environment or {}).items()}
        self._environment_file = str(Path(environment_file).expanduser()) if environment_file else None
        self._workspace_dotenv_cache: tuple[float, dict[str, str]] | None = None
        self._workspace_dotenv_ttl = 2.0

        if extra_run_args:
            logger.debug("extra_run_args currently unused by docker-py binding: %s", extra_run_args)

        ensure_docker_image(image, client=self._client)
        self._container = self._acquire_container()

        self._container_id: str = str(self._container.id)
        # Ensure the in-container workspace directory exists (container FS only).
        self._container.exec_run(
            cmd=["bash", "-lc", f"mkdir -p {shlex.quote(self._workspace_root)}"],
            workdir="/",
        )
        _live_sandboxes.add(self)
        _register_atexit()
        logger.info(
            "DockerSandbox ready container=%s name=%s scope=%s image=%s workspace_path=%s "
            "network=%s volumes=%s previewable=%s reused=%s",
            self._container_id[:12],
            self._container_name or "(ephemeral)",
            self._sandbox_scope,
            image,
            self._workspace_root,
            "enabled" if allow_network else "none",
            "user" if volumes else "none",
            self.previewable,
            getattr(self, "_reused", False),
        )

    # -- container acquire / reuse ------------------------------------------

    def _acquire_container(self) -> Any:
        name = self._container_name
        if name:
            existing = self._get_named_container(name)
            if existing is not None:
                if self._ensure_running(existing):
                    self._reused = True
                    return existing
                # Start failed — keep the orphan under a new name, then create.
                orphan = f"{name}.orphan.{int(time.time())}"
                with contextlib.suppress(Exception):
                    existing.rename(_sanitize_container_name(orphan))
                logger.warning(
                    "DockerSandbox could not start %s; renamed to %s and creating fresh",
                    name,
                    orphan,
                )
        self._reused = False
        return self._create_container()

    def _get_named_container(self, name: str) -> Any | None:
        try:
            return self._client.containers.get(name)
        except self._docker.errors.NotFound:
            return None

    def _ensure_running(self, container: Any) -> bool:
        try:
            container.reload()
        except Exception:  # a stale or removed container is simply not running; pylint: disable=broad-except
            return False
        status = str(getattr(container, "status", "") or "").lower()
        if status == "running":
            return True
        try:
            container.start()
            with contextlib.suppress(Exception):
                container.reload()
            # start() without error is success; status may lag on some clients.
            return True
        except Exception as exc:  # docker SDK error types vary; pylint: disable=broad-except
            logger.warning(
                "Failed to start container %s: %s",
                getattr(container, "name", "?"),
                exc,
            )
            return False

    def _create_container(self) -> Any:
        labels: dict[str, str] = {
            _LABEL_SANDBOX: "1",
            _LABEL_SCOPE: self._sandbox_scope,
        }
        if self._agent_id:
            labels[_LABEL_AGENT_ID] = self._agent_id
        run_kwargs: dict[str, Any] = {
            "image": self._image,
            "command": ["sleep", "infinity"],
            "detach": True,
            "working_dir": self._workspace_root,
            "tty": False,
            "stdin_open": False,
            "labels": labels,
        }
        if self._container_name:
            run_kwargs["name"] = self._container_name
        if self._auto_remove:
            run_kwargs["auto_remove"] = True
        if self._volumes:
            run_kwargs["volumes"] = self._volumes
        if not self._allow_network:
            run_kwargs["network_mode"] = "none"
        if self._memory is not None:
            run_kwargs["mem_limit"] = self._memory
        if self._cpus is not None:
            run_kwargs["nano_cpus"] = int(self._cpus * 1e9)
        if self._pids_limit is not None:
            run_kwargs["pids_limit"] = self._pids_limit
        return self._client.containers.run(**run_kwargs)

    def _rebind_if_missing(self) -> None:
        """Re-acquire when the container vanished; restart if stopped."""
        try:
            self._container.reload()
        except self._docker.errors.NotFound:
            logger.warning(
                "DockerSandbox container missing; re-acquiring name=%s",
                self._container_name or "(ephemeral)",
            )
            self._container = self._acquire_container()
            self._container_id = str(self._container.id)
            self._container.exec_run(
                cmd=["bash", "-lc", f"mkdir -p {shlex.quote(self._workspace_root)}"],
                workdir="/",
            )
            return
        except Exception:  # keep the existing handle when reload fails; pylint: disable=broad-except
            logger.debug("DockerSandbox reload failed; keeping handle", exc_info=True)
            return

        status = str(getattr(self._container, "status", "") or "").lower()
        if status == "running":
            return
        if self._ensure_running(self._container):
            return
        # Start failed — named agents go through orphan+create; ephemeral creates fresh.
        self._container = self._acquire_container()
        self._container_id = str(self._container.id)
        self._container.exec_run(
            cmd=["bash", "-lc", f"mkdir -p {shlex.quote(self._workspace_root)}"],
            workdir="/",
        )

    # -- BaseSandbox abstract API -------------------------------------------

    @property
    def id(self) -> str:
        return f"docker:{self._container_id[:12]}"

    def execute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        self._ensure_open()
        effective = max(1, int(timeout if timeout is not None else self._command_timeout))
        try:
            exec_id = self._client.api.exec_create(
                self._container.id,
                cmd=["bash", "-lc", command],
                workdir=self._workspace_root,
                environment=self._resolve_execute_env(),
            )["Id"]
        except self._docker.errors.APIError as exc:
            return ExecuteResponse(
                output=f"docker exec failed: {exc}",
                exit_code=1,
                truncated=False,
            )

        box: dict[str, Any] = {"output": b"", "error": None}

        def _run() -> None:
            try:
                box["output"] = self._client.api.exec_start(exec_id, demux=False)
            except Exception as exc:  # forwarded to the worker thread below; pylint: disable=broad-except
                box["error"] = exc

        worker = threading.Thread(target=_run, name="docker-exec", daemon=True)
        worker.start()
        worker.join(effective)
        if worker.is_alive():
            self._kill_exec(exec_id)
            worker.join(5)
            return ExecuteResponse(
                output=f"Command timed out after {effective}s",
                exit_code=124,
                truncated=True,
            )

        if box["error"] is not None:
            return ExecuteResponse(
                output=f"docker exec failed: {box['error']}",
                exit_code=1,
                truncated=False,
            )

        raw = box["output"]
        text = bytes(raw).decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw or "")

        truncated = False
        if len(text.encode("utf-8")) > self._max_output_bytes:
            encoded = text.encode("utf-8")[: self._max_output_bytes]
            text = encoded.decode("utf-8", errors="replace") + "\n[output truncated]"
            truncated = True

        exit_code: int | None = None
        with contextlib.suppress(Exception):
            inspected = self._client.api.exec_inspect(exec_id)
            code = inspected.get("ExitCode")
            if code is not None:
                exit_code = int(code)

        return ExecuteResponse(
            output=text,
            exit_code=exit_code,
            truncated=truncated,
        )

    def _kill_exec(self, exec_id: str) -> None:
        """Best-effort kill of a timed-out exec process inside the container."""
        try:
            info = self._client.api.exec_inspect(exec_id)
            pid = info.get("Pid")
            if pid:
                self._container.exec_run(
                    cmd=["bash", "-lc", f"kill -9 {int(pid)} 2>/dev/null || true"],
                    workdir="/",
                )
        except Exception:  # best-effort kill of a timed-out exec; pylint: disable=broad-except
            logger.debug("Failed to kill timed-out exec %s", exec_id, exc_info=True)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        self._ensure_open()
        responses: list[FileUploadResponse] = []
        for path, data in files:
            mapped = self._map_path(path)
            try:
                self._put_file(mapped, data)
                responses.append(FileUploadResponse(path=path))
            except FileNotFoundError:
                responses.append(FileUploadResponse(path=path, error="file_not_found"))
            except PermissionError:
                responses.append(FileUploadResponse(path=path, error="permission_denied"))
            except IsADirectoryError:
                responses.append(FileUploadResponse(path=path, error="is_directory"))
            except Exception as exc:  # docker SDK error types vary; pylint: disable=broad-except
                logger.warning("upload_files failed for %s: %s", path, exc)
                responses.append(FileUploadResponse(path=path, error="invalid_path"))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        self._ensure_open()
        responses: list[FileDownloadResponse] = []
        for path in paths:
            mapped = self._map_path(path)
            try:
                content = self._get_file(mapped)
                responses.append(FileDownloadResponse(path=path, content=content))
            except FileNotFoundError:
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="file_not_found"),
                )
            except PermissionError:
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="permission_denied"),
                )
            except IsADirectoryError:
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="is_directory"),
                )
            except Exception as exc:  # docker SDK error types vary; pylint: disable=broad-except
                logger.warning("download_files failed for %s: %s", path, exc)
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="invalid_path"),
                )
        return responses

    # -- path mapping (in-container workspace path parameter) ---------------

    def _clamp_to_workspace(self, container_path: str) -> str:
        """Keep *container_path* under ``_workspace_root`` (path arg, not a host mount)."""
        root = self._workspace_root
        normalized = _normalize_container_path(container_path)
        if normalized == root or normalized.startswith(root + "/"):
            return normalized
        return root

    def _map_path(self, path: str) -> str:
        """Map virtual agent paths onto the in-container workspace directory.

        The workspace root (explicit ``workspace_path``, else mirrored
        ``workspace_dir``, else ``/workspace``) is only a path argument inside
        the sandbox — not a host bind mount. File I/O always goes through the
        Docker SDK against that container path.
        """
        root = self._workspace_root
        raw = (path or "").strip().replace("\\", "/")
        if not raw or raw in {".", "./", "/"}:
            return root

        if raw == root or raw.startswith(root + "/"):
            return self._clamp_to_workspace(raw)

        if not raw.startswith("/"):
            rel = raw.lstrip("./")
            if not rel or rel == ".":
                return root
            return self._clamp_to_workspace(f"{root}/{rel}")

        return self._clamp_to_workspace(f"{root}{raw}")

    def _to_virtual_path(self, container_or_any: str) -> str:
        """Container ``{workspace}/foo`` → virtual ``/foo`` for BackendWorkspace.

        Does **not** re-home foreign container paths (e.g. ``/bin``) under the
        workspace — that would make a root listing look like workspace entries.
        """
        root = self._workspace_root
        raw = (container_or_any or "").strip().replace("\\", "/")
        if not raw or raw in {".", "./"}:
            return "/"
        if raw.startswith("/"):
            normalized = _normalize_container_path(raw)
        else:
            normalized = _normalize_container_path(f"{root}/{raw.lstrip('./')}")
        if normalized == root:
            return "/"
        prefix = root + "/"
        if normalized.startswith(prefix):
            return f"/{normalized[len(prefix) :]}"
        # Already a virtual key (``/SOUL.md``) or an out-of-workspace path.
        if raw.startswith("/") and not raw.startswith(root):
            return raw
        return "/"

    def _rewrite_entry_path(self, entry: Any) -> Any:
        if isinstance(entry, dict):
            path = entry.get("path")
            if path is None:
                return entry
            return {**entry, "path": self._to_virtual_path(str(path))}
        path = getattr(entry, "path", None)
        if path is None:
            return entry
        virtual = self._to_virtual_path(str(path))
        try:
            entry.path = virtual
        except AttributeError:
            return entry
        return entry

    def _rewrite_ls_result(self, result: Any) -> Any:
        from deepagents.backends.protocol import LsResult

        err = getattr(result, "error", None)
        entries = getattr(result, "entries", None) or []
        return LsResult(
            error=err,
            entries=[self._rewrite_entry_path(e) for e in entries],
        )

    def _rewrite_glob_result(self, result: Any) -> Any:
        from deepagents.backends.protocol import GlobResult

        err = getattr(result, "error", None)
        matches = getattr(result, "matches", None) or []
        return GlobResult(
            error=err,
            matches=[self._rewrite_entry_path(e) for e in matches],
        )

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> Any:
        return super().read(self._map_path(file_path), offset=offset, limit=limit)

    def write(self, file_path: str, content: str) -> Any:
        result = super().write(self._map_path(file_path), content)
        self._invalidate_workspace_dotenv(file_path)
        return result

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> Any:
        result = super().edit(
            self._map_path(file_path),
            old_string,
            new_string,
            replace_all=replace_all,
        )
        self._invalidate_workspace_dotenv(file_path)
        return result

    def ls(self, path: str) -> Any:
        return self._rewrite_ls_result(super().ls(self._map_path(path)))

    def glob(self, pattern: str, path: str | None = None) -> Any:
        return self._rewrite_glob_result(super().glob(pattern, self._map_path(path if path is not None else "/")))

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> Any:
        mapped = self._map_path(path) if path is not None else self._workspace_root
        return super().grep(pattern, path=mapped, glob=glob, max_count=max_count)

    # deepagents>=0.6.12 implements BaseSandbox.als/aglob/… via aexecute with the
    # raw path, bypassing our sync overrides. Always route async I/O through the
    # mapped sync methods so BackendWorkspace.als cannot list container ``/``.
    async def als(self, path: str) -> Any:
        return await asyncio.to_thread(self.ls, path)

    async def aglob(self, pattern: str, path: str | None = None) -> Any:
        return await asyncio.to_thread(self.glob, pattern, path if path is not None else "/")

    async def agrep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> Any:
        return await asyncio.to_thread(self.grep, pattern, path, glob, max_count=max_count)

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> Any:
        return await asyncio.to_thread(self.read, file_path, offset, limit)

    async def awrite(self, file_path: str, content: str) -> Any:
        return await asyncio.to_thread(self.write, file_path, content)

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> Any:
        return await asyncio.to_thread(
            self.edit,
            file_path,
            old_string,
            new_string,
            replace_all,
        )

    def mkdir_path(self, path: str) -> None:
        mapped = self._map_path(path)
        result = self.execute(f"mkdir -p {shlex.quote(mapped)}")
        if result.exit_code not in (0, None):
            raise OSError(result.output or f"mkdir failed for {path!r}")

    def delete_path(self, path: str) -> None:
        mapped = self._map_path(path)
        result = self.execute(f"rm -rf {shlex.quote(mapped)}")
        if result.exit_code not in (0, None):
            raise OSError(result.output or f"delete failed for {path!r}")

    def move_path(self, src: str, dest: str) -> None:
        src_m = self._map_path(src)
        dest_m = self._map_path(dest)
        result = self.execute(
            f"mkdir -p {shlex.quote(str(PurePosixPath(dest_m).parent))} && "
            f"mv {shlex.quote(src_m)} {shlex.quote(dest_m)}"
        )
        if result.exit_code not in (0, None):
            raise OSError(result.output or f"move failed for {src!r} -> {dest!r}")

    # -- lifecycle ----------------------------------------------------------

    def _detach(self) -> None:
        """Drop the Python handle without touching the Docker container."""
        with self._lock:
            self._closed = True
            _live_sandboxes.discard(self)

    def close(self) -> None:
        """Detach this wrapper (idempotent).

        Persistent agent sandboxes are left running and are never removed.
        Ephemeral sandboxes (``auto_remove=True``, typically probes/browse)
        may still be stopped+removed when explicitly configured that way.
        """
        with self._lock:
            if self._closed:
                return
            self._closed = True
            container = getattr(self, "_container", None)
            if container is not None and self._auto_remove:
                with contextlib.suppress(Exception):
                    container.stop(timeout=5)
                with contextlib.suppress(Exception):
                    container.remove(force=True)
            _live_sandboxes.discard(self)

    def destroy(self) -> None:
        """Stop and remove the container (workspace files in container FS go with it).

        Idempotent. After destroy the sandbox is closed and cannot be reused;
        a later :class:`DockerSandbox` with the same name will create fresh.
        """
        with self._lock:
            container = getattr(self, "_container", None)
            self._closed = True
            _live_sandboxes.discard(self)
            if container is None:
                return
            with contextlib.suppress(Exception):
                container.stop(timeout=5)
            with contextlib.suppress(Exception):
                container.remove(force=True)
            self._container = None

    def __enter__(self) -> DockerSandbox:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def __del__(self) -> None:  # pragma: no cover - destructor must not raise
        with contextlib.suppress(Exception):
            self._detach()

    # -- internals ----------------------------------------------------------

    def _invalidate_workspace_dotenv(self, file_path: str) -> None:
        name = PurePosixPath(str(file_path).replace("\\", "/")).name
        if name == ".env":
            self._workspace_dotenv_cache = None

    def _global_env_from_file(self) -> dict[str, str]:
        path = self._environment_file
        if not path:
            return {}
        return load_dotenv_path(path)

    def _workspace_dotenv(self) -> dict[str, str]:
        now = time.monotonic()
        cached = self._workspace_dotenv_cache
        if cached is not None and now - cached[0] < self._workspace_dotenv_ttl:
            return cached[1]
        rels = [".env"]
        if self._system_files_path:
            rels.insert(0, f"{self._system_files_path}/.env")
        raw: bytes | None = None
        for rel in rels:
            try:
                raw = self._get_file(self._map_path(rel))
                break
            except FileNotFoundError:
                continue
            except Exception:  # workspace .env is optional; pylint: disable=broad-except
                logger.debug("DockerSandbox could not read workspace .env", exc_info=True)
                raw = None
                break
        if raw is None:
            values = {}
        else:
            try:
                values = parse_env_text(raw.decode("utf-8", errors="replace"))
            except Exception:  # malformed .env is ignored; pylint: disable=broad-except
                logger.debug("DockerSandbox failed to parse workspace .env", exc_info=True)
                values = {}
        # Missing and present files share the TTL so execute-created ``.env``
        # is picked up without a Docker archive round-trip on every command.
        self._workspace_dotenv_cache = (now, values)
        return values

    def _resolve_execute_env(self) -> dict[str, str]:
        file_env = self._global_env_from_file()
        extra = dict(file_env)
        extra.update(self._environment)
        return resolve_docker_execute_env(
            global_env=extra,
            workspace_env=self._workspace_dotenv(),
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("DockerSandbox is closed")
        self._rebind_if_missing()

    def _put_file(self, container_path: str, data: bytes) -> None:
        parent = str(PurePosixPath(container_path).parent)
        name = PurePosixPath(container_path).name
        self._container.exec_run(
            cmd=["bash", "-lc", f"mkdir -p {shlex.quote(parent)}"],
            workdir=self._workspace_root,
        )
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        buf.seek(0)
        ok = self._container.put_archive(parent, buf.getvalue())
        if not ok:
            raise OSError(f"put_archive failed for {container_path}")

    def _get_file(self, container_path: str) -> bytes:
        try:
            bits, _stat = self._container.get_archive(container_path)
        except self._docker.errors.NotFound as exc:
            raise FileNotFoundError(container_path) from exc

        raw = b"".join(bits)
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r") as tar:
            members = tar.getmembers()
            if not members:
                raise FileNotFoundError(container_path)
            member = members[0]
            if member.isdir():
                raise IsADirectoryError(container_path)
            extracted = tar.extractfile(member)
            if extracted is None:
                raise FileNotFoundError(container_path)
            return extracted.read()


__all__ = [
    "DockerSandbox",
    "SandboxScope",
    "ensure_docker_image",
    "resolve_container_name",
    "resolve_sandbox_name",
]
