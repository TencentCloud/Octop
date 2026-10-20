"""Backend resolution: turn a ``backend`` config value into a real backend instance.

Per design discussion (round 3):
    - Users pass strings (``"local_shell"``, ``"filesystem"``, ``"state"``,
      ``"store"``, ``"composite"``, ``"s3"``, ``"postgres"``) **or** dicts
      with a ``"type"`` field plus per-type kwargs.
    - The default is ``"local_shell"`` rooted at ``"/"``. This gives the
      agent full host access by default; restrict via ``backend.root_dir``
      in production.
    - When resolved with a ``workspace_dir``, local backends are wrapped in
      a :class:`MountedCompositeBackend` whose ``artifacts_root`` points at
      the agent workspace (optionally under ``system_files_path``, e.g.
      ``{workspace}/.octop``). deepagents summarization / filesystem
      middleware then store conversation history, media, and large
      tool-result offloads with skills / sessions — not under the backend
      ``root_dir`` alone (host ``/`` is often not writable on macOS; a
      custom home-scoped ``root_dir`` would otherwise pollute ``~/``).
    - Local-class backends (``local_shell`` / ``filesystem``) accept
      ``root_dir`` in their spec. When the spec doesn't pin a root, the
      caller-supplied ``workspace_dir`` is used instead — keeping a
      ``HarnessAgent(config=...)`` with default backend rooted at the
      configured workspace. ``local_shell`` uses ``BubbledLocalShellBackend``
      only when ``resolve_bubbled_bwrap`` succeeds (Linux + ``virtual_mode`` +
      non-host ``root_dir`` + ``bwrap``); otherwise ``HarnessLocalShellBackend``
      conservatively translates credible virtual command / environment paths
      onto ``root_dir`` and executes from the host workspace.
    - Remote backends (``s3`` / ``postgres`` / ``cos``) ignore ``root_dir``
      entirely; they have their own addressing scheme (``bucket`` /
      ``prefix`` / host + table).
    - Pre-constructed backend instances (anything that quacks like
      ``BackendProtocol``) bypass the factory entirely.

COS users use ``type="s3"`` and pass ``endpoint_url="https://cos.<region>.myqcloud.com"``
plus ``addressing_style="virtual"``; no separate ``COSBackend`` is needed
because Tencent Cloud COS is fully S3-protocol compatible for the operations
this backend uses (put/get/list/delete/head/multipart).
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from octop_harness.backends.composite import MountedCompositeBackend

if TYPE_CHECKING:
    from deepagents.backends.protocol import BackendProtocol

logger = logging.getLogger(__name__)

# One warning per workspace for the life of the process. Agent startup builds
# the same host-root shell more than once, and each build used to log again.
_HOST_ROOT_WARNED: set[str] = set()
_HOST_ROOT_WARN_LOCK = threading.Lock()

# String aliases that callers can use in ``HarnessAgentConfig.backend``.
_BUILTIN_TYPES: frozenset[str] = frozenset(
    {
        "local_shell",  # default
        "filesystem",
        "state",
        "store",
        "composite",
        "s3",
        "postgres",
        "cos",  # Tencent Cloud COS (uses official cos-python-sdk-v5)
        "oss",  # Alibaba Cloud OSS (uses official oss2)
        "obs",  # Huawei Cloud OBS (uses official esdk-obs-python)
        "docker",  # agent-scoped Docker sandbox ([docker] extra)
        "opensandbox",  # remote OpenSandbox ([opensandbox] extra)
    },
)

# Host-wide virtual root. deepagents middleware writes conversation history
# under ``{artifacts_root}/conversation_history``; without a workspace-scoped
# composite wrap that lands relative to the backend ``root_dir`` (often the
# real filesystem root, or a home directory when ``root_dir`` is narrowed).
_HOST_ROOT = "/"


# Applied when ``HarnessAgentConfig.backend`` is ``None`` (``resolve_backend(None)``).
DEFAULT_BACKEND_SPEC: dict[str, Any] = {
    "type": "local_shell",
    "root_dir": _HOST_ROOT,
    "virtual_mode": True,
}


def resolve_backend(
    spec: Any,
    *,
    workspace_dir: str | Path | None = None,
    system_files_path: str = "",
    _scope_host_artifacts: bool = True,
    explicit_virtual_paths: bool = False,
) -> BackendProtocol:
    """Turn a user-provided backend spec into a ``BackendProtocol`` instance.

    Args:
        spec: One of:
            - ``None`` → :data:`DEFAULT_BACKEND_SPEC` is used.
            - A string from ``_BUILTIN_TYPES``.
            - A dict with a ``"type"`` field and per-type kwargs.
            - An object that already implements ``BackendProtocol`` (returned as-is).
        workspace_dir: Used by local-class backends as their ``root_dir``
            when the spec doesn't pin one. Ignored by remote backends.
            When set, also becomes the base for ``artifacts_root`` on a
            wrapping composite backend so deepagents offloads land under the
            agent workspace (see ``system_files_path``).
        system_files_path: Optional workspace-relative prefix (e.g. ``.octop``)
            for offload artifacts, matching skills / sessions layout. Empty
            keeps ``conversation_history`` at the workspace root (legacy).
        _scope_host_artifacts: Internal. When ``False``, skip the workspace
            artifacts wrap (used while resolving composite sub-backends so
            nesting does not double-wrap).

    Returns:
        A concrete backend instance ready to be passed to ``create_deep_agent``.

    Raises:
        ValueError: For unknown types or malformed specs.
        ImportError: For ``postgres`` when ``psycopg`` is not installed.
    """
    if spec is None:
        spec = DEFAULT_BACKEND_SPEC

    if isinstance(spec, str):
        spec = {"type": spec}

    if isinstance(spec, dict):
        if "type" not in spec:
            raise ValueError(
                "Backend spec dict must include a 'type' key (e.g. {'type': 'filesystem'}).",
            )
    elif _looks_like_backend_instance(spec):
        # Pre-built backend object — trust it.
        return spec  # type: ignore[no-any-return]
    else:
        raise ValueError(
            f"Backend spec must be None, a string, a dict with a 'type' key, "
            f"or a BackendProtocol instance; got {type(spec).__name__}.",
        )

    backend_type = spec["type"]
    if backend_type not in _BUILTIN_TYPES:
        raise ValueError(
            f"Unknown backend type {backend_type!r}; expected one of {sorted(_BUILTIN_TYPES)}",
        )

    # Per-type kwargs (everything except 'type').
    kwargs = {k: v for k, v in spec.items() if k != "type"}
    if backend_type == "local_shell":
        return _build_local_shell(
            kwargs,
            workspace_dir=workspace_dir,
            system_files_path=system_files_path,
            scope_host_artifacts=_scope_host_artifacts,
            explicit_virtual_paths=explicit_virtual_paths,
        )
    if backend_type == "filesystem":
        return _build_filesystem(
            kwargs,
            workspace_dir=workspace_dir,
            system_files_path=system_files_path,
            scope_host_artifacts=_scope_host_artifacts,
            explicit_virtual_paths=explicit_virtual_paths,
        )
    if backend_type == "state":
        return _build_state(kwargs)
    if backend_type == "store":
        return _build_store(kwargs)
    if backend_type == "composite":
        return _build_composite(
            kwargs,
            workspace_dir=workspace_dir,
            system_files_path=system_files_path,
            explicit_virtual_paths=explicit_virtual_paths,
        )
    if backend_type == "s3":
        return _build_s3(kwargs)
    if backend_type == "postgres":
        return _build_postgres(kwargs)
    if backend_type == "cos":
        return _build_cos(kwargs)
    if backend_type == "oss":
        return _build_oss(kwargs)
    if backend_type == "obs":
        return _build_obs(kwargs)
    if backend_type == "docker":
        return _build_docker(kwargs, workspace_dir=workspace_dir)
    if backend_type == "opensandbox":
        return _build_opensandbox(kwargs)
    # Unreachable: ``backend_type`` was already validated against ``_BUILTIN_TYPES``.
    raise AssertionError(f"unhandled backend type {backend_type!r}")  # pragma: no cover


# ---------------------------------------------------------------------------
# Per-type builders
# ---------------------------------------------------------------------------


def _artifacts_host_target(
    workspace_dir: str | Path,
    *,
    system_files_path: str = "",
) -> Path:
    """On-disk directory that should hold deepagents offload artifacts."""
    from octop_harness.backends.workspace import normalize_system_files_path

    ws = Path(workspace_dir).expanduser().resolve()
    prefix = normalize_system_files_path(system_files_path)
    return ws / prefix if prefix else ws


def _artifacts_root_for_workspace(
    workspace_dir: str | Path,
    *,
    root_dir: str | Path | None = None,
    system_files_path: str = "",
    explicit_virtual_paths: bool = False,
) -> str | None:
    """Backend path prefix for deepagents offloads, or ``None`` if unmappable.

    deepagents writes ``{artifacts_root}/conversation_history/…``. The value
    must be expressible through the backend's virtual root:

    - ``root_dir == "/"`` → host-absolute workspace (paths equal OS paths)
    - otherwise → workspace-relative virtual path under ``root_dir``
      (e.g. ``/.octop/workspaces/<id>/.octop`` when rooted at ``$HOME``)
    """
    host_target = _artifacts_host_target(workspace_dir, system_files_path=system_files_path)
    if root_dir is None:
        return str(host_target)

    root = Path(root_dir).expanduser().resolve()
    if not explicit_virtual_paths and root == Path(_HOST_ROOT).resolve():
        # Host-rooted backend: offloads must be redirected to the workspace
        # (host '/' is often not writable, e.g. macOS).
        return str(host_target)

    # Non-host root: scope offloads only when an explicit ``system_files_path``
    # prefix is set (e.g. ``.octop``). Otherwise the workspace already sits at
    # the backend root (or is nested under it) and a wrap would be a no-op that
    # only changes the returned backend type — keep the bare backend.
    from octop_harness.backends.workspace import normalize_system_files_path

    if not normalize_system_files_path(system_files_path):
        return None

    try:
        rel = host_target.relative_to(root)
    except ValueError:
        logger.warning(
            "workspace artifacts path %s is outside backend root_dir %s; skipping artifacts_root wrap",
            host_target,
            root,
        )
        return None
    return "/" + rel.as_posix()


def _maybe_wrap_workspace_artifacts(
    backend: BackendProtocol,
    *,
    root_dir: str | Path,
    workspace_dir: str | Path | None,
    system_files_path: str = "",
    scope_host_artifacts: bool,
    explicit_virtual_paths: bool = False,
) -> BackendProtocol:
    """Scope deepagents offloads to the agent workspace (under system_files_path)."""
    if not scope_host_artifacts or workspace_dir is None:
        return backend
    artifacts_root = _artifacts_root_for_workspace(
        workspace_dir,
        root_dir=root_dir,
        system_files_path=system_files_path,
        explicit_virtual_paths=explicit_virtual_paths,
    )
    if artifacts_root is None:
        return backend
    return MountedCompositeBackend(
        default=backend,
        routes={},
        artifacts_root=artifacts_root,
    )


def _warn_host_root_once(workspace_dir: str | Path | None) -> None:
    """Log the host-root shell warning at most once per workspace."""
    key = "<none>" if workspace_dir is None else str(workspace_dir)
    with _HOST_ROOT_WARN_LOCK:
        if key in _HOST_ROOT_WARNED:
            return
        _HOST_ROOT_WARNED.add(key)
    logger.warning(
        "⚠️  LocalShellBackend is rooted at '/' (workspace=%s): the agent has shell access "
        "to the entire host. Restrict ``backend.root_dir`` in production to limit exposure.",
        key,
    )


def _build_local_shell(
    kwargs: dict[str, Any],
    *,
    workspace_dir: str | Path | None,
    system_files_path: str = "",
    scope_host_artifacts: bool = True,
    explicit_virtual_paths: bool = False,
) -> BackendProtocol:
    from octop_harness.backends.bwrap_shell import (
        BubbledLocalShellBackend,
        resolve_bubbled_bwrap,
    )
    from octop_harness.backends.local_shell import HarnessLocalShellBackend, is_host_root

    root_dir = kwargs.pop("root_dir", None)
    if root_dir is None:
        root_dir = workspace_dir if workspace_dir is not None else _HOST_ROOT
    virtual_mode = kwargs.pop("virtual_mode", True)
    # Spec may pin system_files_path (docker / bubbled); prefer explicit kwarg.
    spec_system = kwargs.pop("system_files_path", None)
    effective_system = str(spec_system if spec_system is not None else system_files_path or "")
    kwargs.setdefault("inherit_env", True)

    if is_host_root(root_dir):
        _warn_host_root_once(workspace_dir)

    from_spec = bool(kwargs.pop("explicit_virtual_paths", False))
    shell_kwargs: dict[str, Any] = {
        "root_dir": str(root_dir),
        "virtual_mode": virtual_mode,
        "workspace_dir": workspace_dir,
        "explicit_virtual_paths": explicit_virtual_paths or from_spec,
        **kwargs,
    }
    bwrap = resolve_bubbled_bwrap(virtual_mode=bool(virtual_mode), root_dir=root_dir)
    if bwrap is not None:
        backend: BackendProtocol = BubbledLocalShellBackend(
            bwrap_path=bwrap,
            system_files_path=effective_system,
            **shell_kwargs,
        )
    else:
        backend = HarnessLocalShellBackend(**shell_kwargs)
    return _maybe_wrap_workspace_artifacts(
        backend,
        root_dir=root_dir,
        workspace_dir=workspace_dir,
        system_files_path=effective_system,
        scope_host_artifacts=scope_host_artifacts,
        explicit_virtual_paths=bool(shell_kwargs["explicit_virtual_paths"]),
    )


def _build_filesystem(
    kwargs: dict[str, Any],
    *,
    workspace_dir: str | Path | None,
    system_files_path: str = "",
    scope_host_artifacts: bool = True,
    explicit_virtual_paths: bool = False,
) -> BackendProtocol:
    from deepagents.backends import FilesystemBackend

    root_dir = kwargs.pop("root_dir", None)
    if root_dir is None:
        root_dir = workspace_dir if workspace_dir is not None else _HOST_ROOT
    virtual_mode = kwargs.pop("virtual_mode", True)
    spec_system = kwargs.pop("system_files_path", None)
    effective_system = str(spec_system if spec_system is not None else system_files_path or "")
    kwargs.pop("explicit_virtual_paths", None)
    backend = FilesystemBackend(root_dir=str(root_dir), virtual_mode=virtual_mode, **kwargs)
    return _maybe_wrap_workspace_artifacts(
        backend,
        root_dir=root_dir,
        workspace_dir=workspace_dir,
        system_files_path=effective_system,
        scope_host_artifacts=scope_host_artifacts,
        explicit_virtual_paths=explicit_virtual_paths,
    )


def _build_state(kwargs: dict[str, Any]) -> BackendProtocol:
    from deepagents.backends import StateBackend

    return StateBackend(**kwargs)


def _build_store(kwargs: dict[str, Any]) -> BackendProtocol:
    from deepagents.backends import StoreBackend

    # Convenience: accept ``namespace=("user", "thread")`` (a tuple) and wrap it
    # in a callable that the deepagents API expects.
    namespace = kwargs.pop("namespace", None)
    if namespace is not None and not callable(namespace):
        ns_tuple: tuple[str, ...] = tuple(namespace)
        kwargs["namespace"] = lambda _runtime: ns_tuple

    return StoreBackend(**kwargs)


def _build_composite(
    kwargs: dict[str, Any],
    *,
    workspace_dir: str | Path | None,
    system_files_path: str = "",
    explicit_virtual_paths: bool = False,
) -> BackendProtocol:
    default = kwargs.pop("default", None)
    if default is None:
        raise ValueError("composite backend requires a 'default' sub-spec")
    routes = kwargs.pop("routes", {})
    if not isinstance(routes, dict):
        raise ValueError("composite backend 'routes' must be a dict mapping path-prefix -> sub-spec")

    # Sub-backends must not independently wrap for artifacts — the composite owns
    # routing and ``artifacts_root``.
    resolved_default = resolve_backend(
        default,
        workspace_dir=workspace_dir,
        system_files_path=system_files_path,
        _scope_host_artifacts=False,
        explicit_virtual_paths=explicit_virtual_paths,
    )
    resolved_routes = {
        prefix: resolve_backend(
            sub,
            workspace_dir=workspace_dir,
            system_files_path=system_files_path,
            _scope_host_artifacts=False,
            explicit_virtual_paths=explicit_virtual_paths,
        )
        for prefix, sub in routes.items()
    }
    if "artifacts_root" not in kwargs and workspace_dir is not None:
        default_root = getattr(resolved_default, "root_dir", None) or getattr(resolved_default, "cwd", None)
        artifacts_root = _artifacts_root_for_workspace(
            workspace_dir,
            root_dir=default_root,
            system_files_path=system_files_path,
            explicit_virtual_paths=explicit_virtual_paths,
        )
        if artifacts_root is not None:
            kwargs["artifacts_root"] = artifacts_root
    return MountedCompositeBackend(default=resolved_default, routes=resolved_routes, **kwargs)


def spec_supports_execution(spec: Any) -> bool:
    """Predict ``deepagents.supports_execution`` for a backend *spec*.

    Answers "would the resolved backend run shell commands?" without
    instantiating it — useful for callers (e.g. security policies) that only
    need the capability, not a live backend.

    Mirrors the deepagents rule: a ``composite`` spec delegates to its
    ``default`` sub-spec (routes are ignored, as in ``CompositeBackend``), and
    ``local_shell`` / ``docker`` / ``opensandbox`` are the shell-capable builtins. Pre-built
    backend instances are inspected directly.
    """
    if spec is None:
        spec = DEFAULT_BACKEND_SPEC

    if isinstance(spec, str):
        spec = {"type": spec}

    if not isinstance(spec, dict):
        from deepagents.middleware.filesystem import supports_execution

        return supports_execution(cast("BackendProtocol", spec))

    if spec.get("type") == "composite":
        default = spec.get("default")
        return default is not None and spec_supports_execution(default)
    return spec.get("type") in {"local_shell", "docker", "opensandbox"}


def _looks_like_backend_instance(obj: Any) -> bool:
    """Duck-type check: does the object expose the BackendProtocol surface?"""
    return all(hasattr(obj, m) for m in ("read", "write", "ls", "edit", "glob", "grep"))


def _build_s3(kwargs: dict[str, Any]) -> BackendProtocol:
    """S3-compatible backend (AWS S3, MinIO, custom S3-compatible stores).

    Always uses the bundled :class:`~octop_harness.backends.s3_backend.S3Backend`
    (boto3). That implementation speaks the deepagents 0.7 ``BackendProtocol``
    (``WriteResult`` / ``ReadResult`` / ``ls`` / ``glob`` / ``grep``). The
    third-party ``deepagents-backends`` S3 client stays on the 0.5/0.6 protocol
    and must not be selected here.

    Community path-style aliases (``s3_force_path_style`` / ``path_style``)
    are translated by :meth:`S3Config.from_kwargs`. Unknown keys go into
    ``extra`` instead of raising.

    For Alibaba Cloud OSS use ``type="oss"`` and for Huawei Cloud OBS use
    ``type="obs"`` — both have dedicated backends that use the official SDKs.
    """
    from octop_harness.backends.s3_backend import S3Backend as _S3Backend
    from octop_harness.backends.s3_backend import S3Config as _S3Config

    return _S3Backend(_S3Config.from_kwargs(**kwargs))


def _build_postgres(kwargs: dict[str, Any]) -> BackendProtocol:
    """Postgres workspace backend (bundled, deepagents 0.7).

    Specs may use a libpq ``connection_string`` / ``dsn`` or split fields.
    Unknown keys are dropped. The table is created on first use (``psycopg``
    required; install ``octop-harness[remote-backends]``).
    """
    from octop_harness.backends.postgres import PostgresBackend, PostgresConfig

    return PostgresBackend(PostgresConfig.from_kwargs(**kwargs))


def _build_cos(kwargs: dict[str, Any]) -> BackendProtocol:
    """Tencent Cloud COS backend (uses the official ``cos-python-sdk-v5``).

    Available via the ``octop-harness[cos]`` extra. We use the
    official Tencent SDK rather than boto3 to avoid the v4-signature /
    addressing-style pitfalls that hit S3-compatible client libraries.
    """
    try:
        from octop_harness.backends.cos_backend import CosBackend, CosConfig
    except ImportError as exc:
        raise ImportError(
            "COS backend requires the optional dependency 'cos-python-sdk-v5'. "
            "Install with: pip install 'octop-harness[cos]'.",
        ) from exc

    config = CosConfig(**kwargs)
    return CosBackend(config)


def _build_oss(kwargs: dict[str, Any]) -> BackendProtocol:
    """Alibaba Cloud OSS backend (uses the official ``oss2`` SDK).

    Available via the ``octop-harness[oss]`` extra. Uses oss2
    directly instead of boto3 to avoid S3 addressing-style compatibility issues.
    """
    try:
        from octop_harness.backends.oss_backend import OssBackend, OssConfig
    except ImportError as exc:
        raise ImportError(
            "OSS backend requires the optional dependency 'oss2'. Install with: pip install 'octop-harness[oss]'.",
        ) from exc

    config = OssConfig(**kwargs)
    return OssBackend(config)


def _build_obs(kwargs: dict[str, Any]) -> BackendProtocol:
    """Huawei Cloud OBS backend (uses the official ``esdk-obs-python`` SDK).

    Available via the ``octop-harness[obs]`` extra. Uses the Huawei
    SDK directly instead of boto3 to avoid S3 addressing-style compatibility issues.
    """
    try:
        from octop_harness.backends.obs_backend import ObsBackend, ObsConfig
    except ImportError as exc:
        raise ImportError(
            "OBS backend requires the optional dependency 'esdk-obs-python'. "
            "Install with: pip install 'octop-harness[obs]'.",
        ) from exc

    config = ObsConfig(**kwargs)
    return ObsBackend(config)


def _build_docker(
    kwargs: dict[str, Any],
    *,
    workspace_dir: str | Path | None,
) -> BackendProtocol:
    """Agent-scoped Docker sandbox (optional ``[docker]`` extra).

    File tools and ``execute`` run inside the container via the Docker SDK.
    Host ``workspace_dir`` holds sessions/memory; the same absolute path is the
    default in-container agent workspace (not bind-mounted). Optional
    ``volumes`` / ``workspace_path`` come from the spec dict.
    """
    from octop_harness.backends.docker_sandbox import DockerSandbox

    if "workspace_dir" not in kwargs and workspace_dir is not None:
        kwargs["workspace_dir"] = workspace_dir
    return DockerSandbox(**kwargs)


def _build_opensandbox(kwargs: dict[str, Any]) -> BackendProtocol:
    """Remote OpenSandbox (optional ``[opensandbox]`` extra).

    Creates a sandbox on construct; ``close()`` destroys it. File tools and
    ``execute`` run through the official ``opensandbox`` SDK.
    """
    from octop_harness.backends.opensandbox_sandbox import OpenSandbox

    return OpenSandbox(**kwargs)


__all__ = [
    "DEFAULT_BACKEND_SPEC",
    "BackendWorkspace",
    "BubbledLocalShellBackend",
    "HarnessLocalShellBackend",
    "MountedCompositeBackend",
    "ProbeResult",
    "anchor_at_backend_root",
    "cos_spec_to_s3_compat",
    "probe_backend",
    "resolve_backend",
    "spec_supports_execution",
]

from octop_harness.backends.bwrap_shell import BubbledLocalShellBackend
from octop_harness.backends.local_shell import HarnessLocalShellBackend
from octop_harness.backends.probe import ProbeResult, probe_backend
from octop_harness.backends.s3_backend import cos_spec_to_s3_compat
from octop_harness.backends.utils import anchor_at_backend_root
from octop_harness.backends.workspace import BackendWorkspace
