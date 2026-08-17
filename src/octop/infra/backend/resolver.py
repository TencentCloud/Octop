"""Resolve agent ``backend`` config (named refs, composite routes)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from octop.infra.backend.adapter import row_to_backend_spec


def default_agent_backend_spec(workspace_dir: Path) -> dict[str, Any]:
    """Harness backend for agents with no explicit ``backend`` in config.

    On POSIX this matches harness ``DEFAULT_BACKEND_SPEC`` (host-rooted virtual
    paths). harness ``resolve_backend(..., workspace_dir=...)`` wraps that
    host root in a composite whose ``artifacts_root`` is the agent workspace,
    so deepagents conversation history stays writable. On Windows
    ``root_dir='/'`` resolves to the process current-drive root, which often
    differs from the drive hosting ``workspace_dir`` — scope the default to
    the agent workspace instead.

    Windows also sets ``inherit_env=True``: deepagents ``LocalShellBackend``
    defaults to an *empty* subprocess environment (no ``PATH``/``SystemRoot``),
    which makes every external tool — python/curl/ffmpeg/edge-tts — unfindable
    from the agent's ``execute`` tool. This is the path a brand-new agent (no
    explicit ``backend`` config) takes, so it is where the new-user default
    must already work.
    """
    from harness_agent.backends import DEFAULT_BACKEND_SPEC  # noqa: PLC0415

    if os.name == "nt":
        return {
            "type": "local_shell",
            "root_dir": str(workspace_dir.resolve()),
            "virtual_mode": True,
            # Without this every execute() subprocess starts with an empty env
            # (no PATH/SystemRoot), so python/curl/ffmpeg/edge-tts are unfindable.
            "inherit_env": True,
        }
    return dict(DEFAULT_BACKEND_SPEC)


def windows_neutralize_host_root(spec: Any, *, workspace_dir: Path) -> Any:
    """Windows: normalize local host backends so they actually work on the host.

    This is the single normalization point for Windows ``local_shell`` /
    ``filesystem`` agent backends, correcting two defaults that are broken on
    Windows. Applies to top-level specs, composite ``default`` subspecs, and
    the agent-config path that doesn't go through ``default_agent_backend_spec``.
    Route sub-backends are user-pinned and left untouched — a route root of
    ``/`` is the caller's explicit choice and harmless to loading.

    1. Host-root rewrite: ``root_dir: "/"`` is the dashboard's default for local
    backends. On Windows it resolves to the *current drive root* (often a
    different drive than the agent workspace), so deepagents virtual-path checks
    reject every workspace path with ``Path ... outside root directory``. Only
    ``root_dir`` is rewritten; ``type`` / ``virtual_mode`` stay intact.

    2. Empty subprocess env: deepagents ``LocalShellBackend`` defaults
    ``inherit_env=False``, so without intervention every subprocess starts with
    an empty environment (no ``PATH``/``SystemRoot``) and common tools
    (python/curl/ffmpeg/edge-tts) are unfindable. On POSIX ``sh`` fills in a
    default ``PATH``, so the breakage is effectively Windows-specific. Inject
    ``inherit_env`` so the parent server environment is visible to agent shell
    commands — but only as a *default*: an explicitly pinned ``inherit_env`` is
    preserved, so a user who deliberately wants an empty-env sandbox can still
    set it to ``False``. (``filesystem`` never gets this: it has no execute tool
    and its constructor rejects the kwarg.)
    """
    if os.name != "nt":
        return spec
    if not isinstance(spec, dict):
        return spec
    kind = spec.get("type")
    if kind in ("local_shell", "filesystem"):
        out = dict(spec)
        if _is_host_root(spec.get("root_dir")):
            out["root_dir"] = str(workspace_dir.resolve())
        # local_shell runs shell commands on the host; deepagents defaults
        # inherit_env=False, so without this every subprocess has an empty env
        # (no PATH/SystemRoot) and python/curl/ffmpeg/edge-tts are unfindable.
        # filesystem has no execute tool and its constructor rejects this kwarg.
        # setdefault keeps an explicit user override (inherit_env: false).
        if kind == "local_shell":
            out.setdefault("inherit_env", True)
        return out
    if kind == "composite" and isinstance(spec.get("default"), dict):
        new_default = windows_neutralize_host_root(spec["default"], workspace_dir=workspace_dir)
        if new_default is not spec["default"]:
            return {**spec, "default": new_default}
    return spec


def _is_host_root(root: Any) -> bool:
    """True when *root* is an explicitly host-rooted local backend path.

    Only an *explicit* ``/``, ``\\`` or empty string counts (the dashboard's
    default). A missing ``root_dir`` is left alone — harness already falls back
    to ``workspace_dir`` for local backends, which is workspace-scoped by
    design.
    """
    return root is not None and str(root).strip() in ("/", "\\", "")


def resolve_agent_backend_spec(
    spec: Any,
    *,
    repo: Any | None,
) -> Any:
    """Expand ``named`` refs (and composite trees) into harness-ready specs."""
    if spec is None:
        return None
    if not isinstance(spec, dict):
        return spec

    kind = spec.get("type")
    if kind == "named":
        name = spec.get("name")
        if not repo or not name:
            raise ValueError("named backend requires a configured storage backend name")
        row = repo.get_by_name(str(name))
        if row is None:
            raise ValueError(f"storage backend {name!r} not found")
        inner = row_to_backend_spec(row)
        if inner is None:
            raise ValueError(f"storage backend {name!r} is incomplete")
        return resolve_agent_backend_spec(inner, repo=repo)

    if kind == "composite":
        default = spec.get("default")
        if default is None:
            raise ValueError("composite backend requires a default sub-spec")
        routes = spec.get("routes") or {}
        if not isinstance(routes, dict):
            raise ValueError("composite backend routes must be a dict")
        return {
            "type": "composite",
            "default": resolve_agent_backend_spec(default, repo=repo),
            "routes": {
                str(prefix): resolve_agent_backend_spec(sub, repo=repo)
                for prefix, sub in routes.items()
            },
        }

    cleaned = dict(spec)
    if kind not in ("named", "composite") and "name" in cleaned:
        del cleaned["name"]
    return cleaned


def collect_named_storage_backend_refs(spec: Any) -> set[str]:
    """Collect ``storage_backends.name`` values referenced by an agent backend spec tree."""
    if spec is None:
        return set()
    if isinstance(spec, str):
        if spec.startswith("named:"):
            return {spec.split(":", 1)[1]}
        return set()
    if not isinstance(spec, dict):
        return set()
    kind = spec.get("type")
    if kind == "named":
        name = spec.get("name")
        return {str(name)} if name else set()
    if kind == "composite":
        out: set[str] = set()
        out |= collect_named_storage_backend_refs(spec.get("default"))
        routes = spec.get("routes")
        if isinstance(routes, dict):
            for sub in routes.values():
                out |= collect_named_storage_backend_refs(sub)
        return out
    return set()


def find_agents_using_storage_backend(
    *,
    agent_repo: Any,
    get_config: Any,
    backend_name: str,
) -> list[dict[str, str]]:
    """Return agents whose ``config.backend`` references *backend_name* (named / composite)."""
    refs: list[dict[str, str]] = []
    for row in agent_repo.list_all():
        cfg = get_config(row.agent_id)
        if not isinstance(cfg, dict):
            continue
        if backend_name in collect_named_storage_backend_refs(cfg.get("backend")):
            refs.append({"agent_id": row.agent_id, "name": row.name})
    return refs


def backend_spec_supports_execution(spec: Any) -> bool:
    """True when the backend spec resolves to a sandbox/shell backend.

    deepagents ``FilesystemMiddleware`` rejects filesystem ``permissions`` when
    the backend implements ``SandboxBackendProtocol`` (e.g. ``local_shell``).
    """
    if spec is None:
        return True
    if isinstance(spec, str):
        return spec in {"local_shell", "docker"}
    if not isinstance(spec, dict):
        return False
    kind = spec.get("type")
    if kind == "local_shell":
        return True
    if kind == "docker":
        return True
    if kind == "composite":
        if backend_spec_supports_execution(spec.get("default")):
            return True
        routes = spec.get("routes")
        if isinstance(routes, dict):
            return any(backend_spec_supports_execution(route) for route in routes.values())
    return False
