"""Octop helpers for harness ``type: "docker"`` backend specs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

DEFAULT_SANDBOX_PREFIX = "octop_sandbox"

_DOCKER_PASSTHROUGH_KEYS = (
    "allow_network",
    "memory",
    "cpus",
    "pids_limit",
    "command_timeout",
    "max_output_bytes",
    "auto_remove",
    "workspace_path",
    "volumes",
    "environment",
    "environment_file",
    "agent_id",
    "container_name",
    "sandbox_scope",
    "sandbox_prefix",
    "username",
    "sandbox_id",
    "previewable",
)


def apply_docker_cfg_keys(spec: dict[str, Any], cfg: dict[str, Any]) -> None:
    """Copy known docker config keys from *cfg* onto *spec* (in place)."""
    for key in _DOCKER_PASSTHROUGH_KEYS:
        if key in cfg:
            spec[key] = cfg[key]


def docker_spec_previewable(spec: Any) -> bool:
    """Whether Admin storage UI may browse this backend's files (``/admin/backend``).

    Expert workspace preview is always available and does not use this flag.
    Non-docker backends are always browseable. For docker, only ``fixed``
    scope is browseable by default (or an explicit ``previewable`` flag).
    """
    if not isinstance(spec, dict):
        return True
    if str(spec.get("type") or "").lower() != "docker":
        return True
    if "previewable" in spec:
        return bool(spec["previewable"])
    return str(spec.get("sandbox_scope") or "agent").strip().lower() == "fixed"


def enrich_docker_backend_spec(
    spec: dict[str, Any],
    *,
    agent_id: str,
    username: str | None = None,
) -> dict[str, Any]:
    """Inject Octop defaults into a docker harness spec (does not overwrite set keys).

    - ``sandbox_prefix`` defaults to ``octop_sandbox``
    - ``sandbox_scope`` defaults to ``agent``
    - ``agent`` scope: set ``agent_id`` when missing
    - ``user`` scope: set ``username`` from the agent owner when missing
    """
    if str(spec.get("type") or "").lower() != "docker":
        return spec
    out = dict(spec)
    out.setdefault("sandbox_prefix", DEFAULT_SANDBOX_PREFIX)
    scope = str(out.get("sandbox_scope") or "agent").strip().lower() or "agent"
    out.setdefault("sandbox_scope", scope)
    if scope == "agent":
        out.setdefault("agent_id", agent_id)
    elif scope == "user" and username and not out.get("username"):
        out["username"] = username
    return out


def inject_docker_global_environment(
    spec: dict[str, Any],
    env_file: str | Path | None,
) -> dict[str, Any]:
    """Point a docker spec at Admin ``~/.octop/env`` (re-read on each execute)."""
    if str(spec.get("type") or "").lower() != "docker":
        return spec
    out = dict(spec)
    if env_file is not None:
        out["environment_file"] = str(env_file)
    return out
