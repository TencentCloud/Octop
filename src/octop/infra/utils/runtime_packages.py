"""Install optional Python packages into the active interpreter at runtime.

Octop deployments vary: uv venvs often omit ``pip``, systemd services may not
have ``uv`` on ``PATH``, and some hosts only ship the stdlib. Callers should
use :func:`install_packages` / :func:`install_packages_async` instead of
hand-rolling ``pip`` / ``uv pip`` commands.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import logging
import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

INSTALL_TIMEOUT_SEC = 600
_PIP_MISSING_MARKERS = ("No module named pip", "No module named 'pip'")
_INSTALL_LOCK = threading.Lock()

InstallOutcome = Literal["ready", "installed"]


@dataclass(frozen=True)
class PackageInstallSpec:
    """Direct PyPI specs plus an optional ``octop[extra]`` fallback."""

    packages: tuple[str, ...]
    extra_fallback: str | None = None


def find_uv_binary() -> str | None:
    """Resolve ``uv`` from env, PATH, or common install locations."""
    override = os.environ.get("OCTOP_UV_BIN", "").strip()
    if override:
        path = Path(override)
        if path.is_file():
            return str(path)
    found = shutil.which("uv")
    if found:
        return found
    for candidate in _uv_search_paths():
        if candidate.is_file():
            return str(candidate)
    return None


def _uv_search_paths() -> tuple[Path, ...]:
    if os.name == "nt":
        paths: list[Path] = []
        local_app = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app:
            paths.append(Path(local_app) / "Programs" / "uv" / "uv.exe")
        program_files = os.environ.get("PROGRAMFILES", "").strip()
        if program_files:
            paths.append(Path(program_files) / "uv" / "uv.exe")
        paths.extend(
            (
                Path.home() / ".local" / "bin" / "uv.exe",
                Path.home() / ".cargo" / "bin" / "uv.exe",
            )
        )
        return tuple(paths)
    return (
        Path.home() / ".local" / "bin" / "uv",
        Path.home() / ".cargo" / "bin" / "uv",
        Path("/usr/local/bin/uv"),
        Path("/bin/uv"),
    )


def pip_importable() -> bool:
    return importlib.util.find_spec("pip") is not None


def ensure_pip_bootstrapped() -> bool:
    """Best-effort ``ensurepip`` when the interpreter has no ``pip`` module."""
    if pip_importable():
        return True
    logger.info("Bootstrapping pip via ensurepip for %s", sys.executable)
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "ensurepip", "--default-pip"],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return False
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        if detail:
            logger.warning("ensurepip failed: %s", detail[-400:])
        return False
    return pip_importable()


def purge_import_cache(module_names: Sequence[str]) -> None:
    for name in module_names:
        sys.modules.pop(name, None)
    importlib.invalidate_caches()


def build_install_commands(packages: Sequence[str]) -> list[list[str]]:
    """Ordered install strategies for *packages* into ``sys.executable``."""
    specs = list(packages)
    commands: list[list[str]] = []
    uv_bin = find_uv_binary()
    if uv_bin:
        commands.append([uv_bin, "pip", "install", "--python", sys.executable, *specs])
    commands.append(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            *specs,
        ]
    )
    return commands


def _extra_fallback_commands(extra: str) -> list[list[str]]:
    spec = f"octop[{extra}]"
    commands: list[list[str]] = []
    uv_bin = find_uv_binary()
    if uv_bin:
        commands.append([uv_bin, "pip", "install", "--python", sys.executable, spec])
    commands.append(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            spec,
        ]
    )
    return commands


def _pip_missing_output(detail: str) -> bool:
    return any(marker in detail for marker in _PIP_MISSING_MARKERS)


def _run_install_command(cmd: list[str], *, timeout: int) -> tuple[bool, str]:
    logger.info("Installing runtime Python packages: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return False, "timed out"
    if proc.returncode == 0:
        return True, ""
    detail = (proc.stderr or proc.stdout or "").strip()
    if len(detail) > 800:
        detail = detail[-800:]
    return False, detail


def _attempt_install_commands(
    commands: Sequence[Sequence[str]],
    *,
    timeout: int,
) -> tuple[bool, str]:
    last_detail = ""
    pip_bootstrapped = False
    for cmd in commands:
        ok, detail = _run_install_command(list(cmd), timeout=timeout)
        if ok:
            return True, ""
        last_detail = detail
        if _pip_missing_output(detail) and not pip_bootstrapped:
            pip_bootstrapped = ensure_pip_bootstrapped()
            if pip_bootstrapped:
                logger.info("Retrying pip install after ensurepip bootstrap")
                ok, detail = _run_install_command(list(cmd), timeout=timeout)
                if ok:
                    return True, ""
                last_detail = detail
            logger.warning("pip unavailable; trying next installer strategy")
    return False, last_detail


def install_packages(
    spec: PackageInstallSpec | Sequence[str],
    *,
    is_satisfied: Callable[[], bool] | None = None,
    import_modules: Sequence[str] = (),
    timeout: int = INSTALL_TIMEOUT_SEC,
) -> InstallOutcome:
    """Install *spec* into the running interpreter with multiple fallbacks."""
    if isinstance(spec, PackageInstallSpec):
        packages = spec.packages
        extra_fallback = spec.extra_fallback
    else:
        packages = tuple(spec)
        extra_fallback = None

    if is_satisfied is not None and is_satisfied():
        return "ready"

    commands: list[list[str]] = list(build_install_commands(packages))
    if extra_fallback:
        commands.extend(_extra_fallback_commands(extra_fallback))

    with _INSTALL_LOCK:
        if is_satisfied is not None and is_satisfied():
            return "ready"

        ok, detail = _attempt_install_commands(commands, timeout=timeout)
        if import_modules:
            purge_import_cache(import_modules)

        if is_satisfied is not None:
            if not is_satisfied():
                raise RuntimeError(_install_failed_message(detail if not ok else ""))
            return "installed" if ok else "ready"

        if not ok:
            raise RuntimeError(_install_failed_message(detail))
        return "installed"


async def install_packages_async(
    spec: PackageInstallSpec | Sequence[str],
    *,
    is_satisfied: Callable[[], bool] | None = None,
    import_modules: Sequence[str] = (),
    timeout: int = INSTALL_TIMEOUT_SEC,
) -> InstallOutcome:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: install_packages(
            spec,
            is_satisfied=is_satisfied,
            import_modules=import_modules,
            timeout=timeout,
        ),
    )


def build_uninstall_command(packages: Sequence[str]) -> list[str] | None:
    """First-choice uninstall command for *packages*, or ``None`` when unavailable."""
    names = list(packages)
    uv_bin = find_uv_binary()
    if uv_bin:
        return [uv_bin, "pip", "uninstall", "-y", *names, "--python", sys.executable]
    if pip_importable():
        return [sys.executable, "-m", "pip", "uninstall", "-y", *names]
    return None


def _install_failed_message(detail: str) -> str:
    """User-facing failure text — no shell commands."""
    base = (
        "Could not install optional Python components automatically. "
        "Check network access and server logs, then retry."
    )
    if not detail or detail == "timed out":
        return base
    if _pip_missing_output(detail):
        return f"{base} This Python environment has no package installer (pip/uv unavailable)."
    return base
