"""Discover and optionally install the Node LibreOffice Kit helper."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from octop.infra.utils.paths import PathLayout

KIT_VERSION = "0.2.3"
MIN_NODE = (22, 19, 0)

_HELPER_NAMES = ("convert.mjs", "package.json")


@dataclass(frozen=True)
class RuntimeProbe:
    available: bool
    node_bin: str | None
    node_version: str | None
    helper_dir: Path | None
    reason: str


def packaged_helper_dir() -> Path:
    return Path(__file__).resolve().parent / "helper"


def runtime_dir(paths: PathLayout | None = None) -> Path:
    layout = paths if paths is not None else PathLayout.from_env()
    override = os.environ.get("OCTOP_OFFICE_PREVIEW_RUNTIME", "").strip()
    if override:
        return Path(override).expanduser()
    return layout.office_preview_dir


def _parse_node_version(raw: str) -> tuple[int, int, int] | None:
    text = raw.strip()
    if text.startswith("v"):
        text = text[1:]
    parts = text.split(".")
    if len(parts) < 2:
        return None
    try:
        major = int(parts[0])
        minor = int(parts[1])
        patch = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        return None
    return major, minor, patch


def resolve_node_bin() -> str | None:
    override = os.environ.get("OCTOP_OFFICE_PREVIEW_NODE", "").strip()
    if override:
        path = Path(override).expanduser()
        return str(path) if path.is_file() else None
    found = shutil.which("node")
    return found


def _node_version_string(node_bin: str) -> str | None:
    try:
        proc = subprocess.run(
            [node_bin, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return (proc.stdout or proc.stderr or "").strip() or None


def probe_runtime(paths: PathLayout | None = None) -> RuntimeProbe:
    """Fast filesystem / version probe — does not convert a document."""
    node_bin = resolve_node_bin()
    if node_bin is None:
        return RuntimeProbe(False, None, None, None, "node_missing")
    version = _node_version_string(node_bin)
    parsed = _parse_node_version(version or "")
    if parsed is None:
        return RuntimeProbe(False, node_bin, version, None, "node_version_unreadable")
    if parsed < MIN_NODE:
        return RuntimeProbe(False, node_bin, version, None, "node_too_old")
    helper = runtime_dir(paths)
    script = helper / "convert.mjs"
    kit_dir = helper / "node_modules" / "@deepseek-ai" / "libreoffice-kit"
    if not script.is_file():
        return RuntimeProbe(False, node_bin, version, helper, "helper_missing")
    marker = helper / ".kit-version"
    if not kit_dir.is_dir() or not marker.is_file() or marker.read_text().strip() != KIT_VERSION:
        return RuntimeProbe(False, node_bin, version, helper, "kit_missing")
    return RuntimeProbe(True, node_bin, version, helper, "ok")


def probe_status_payload(paths: PathLayout | None = None) -> dict[str, object]:
    probe = probe_runtime(paths)
    return {
        "available": probe.available,
        "node_version": probe.node_version,
        "kit_version": KIT_VERSION,
        "reason": None if probe.available else probe.reason,
    }


def _copy_helper(dest: Path) -> None:
    src = packaged_helper_dir()
    dest.mkdir(parents=True, exist_ok=True)
    for name in _HELPER_NAMES:
        shutil.copy2(src / name, dest / name)


def install_runtime(
    *,
    paths: PathLayout | None = None,
    npm_bin: str | None = None,
) -> Path:
    """Copy the helper and ``npm install`` the pinned kit into the runtime dir.

    Never called from a preview request.
    """
    dest = runtime_dir(paths)
    _copy_helper(dest)
    (dest / ".kit-version").unlink(missing_ok=True)
    npm = npm_bin or shutil.which("npm")
    if not npm:
        raise RuntimeError("npm is not installed")
    node_bin = resolve_node_bin()
    if node_bin is None:
        raise RuntimeError("node is not installed")
    version = _node_version_string(node_bin)
    parsed = _parse_node_version(version or "")
    if parsed is None or parsed < MIN_NODE:
        raise RuntimeError(
            f"office preview needs Node >= {MIN_NODE[0]}.{MIN_NODE[1]}.{MIN_NODE[2]}, "
            f"got {version or 'unknown'}"
        )
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
    }
    proc = subprocess.run(
        [npm, "install", "--omit=dev", "--no-audit", "--no-fund"],
        cwd=dest,
        check=False,
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError("npm install of libreoffice-kit failed")
    (dest / ".kit-version").write_text(KIT_VERSION, encoding="ascii")
    probe = probe_runtime(paths)
    if not probe.available:
        raise RuntimeError(f"office preview runtime still unavailable: {probe.reason}")
    return dest
