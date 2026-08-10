"""Detect / best-effort provision Docker Engine for agent sandbox backends.

Mirrors :mod:`octop.infra.utils.bwrap`: never raise for missing privileges;
return a status payload the dashboard can show with install script / agent prompt.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import sys
from typing import Any

logger = logging.getLogger(__name__)

_INSTALL_TIMEOUT_SEC = 180
_PROBE_TIMEOUT_SEC = 8

_PKG_MANAGERS: tuple[tuple[str, str], ...] = (
    ("apt-get", "apt"),
    ("apt", "apt"),
    ("dnf", "dnf"),
    ("yum", "yum"),
    ("pacman", "pacman"),
    ("zypper", "zypper"),
)

_DOCS_BY_PLATFORM = {
    "linux": "https://docs.docker.com/engine/install/",
    "darwin": "https://docs.docker.com/desktop/setup/install/mac-install/",
    "win32": "https://docs.docker.com/desktop/setup/install/windows-install/",
}


def _platform_key() -> str:
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform.startswith("win"):
        return "win32"
    return sys.platform


def _detect_package_manager() -> str | None:
    for binary, kind in _PKG_MANAGERS:
        if shutil.which(binary):
            return kind
    return None


def _can_install_without_password() -> bool:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return True
    sudo = shutil.which("sudo")
    if sudo is None:
        return False
    try:
        result = subprocess.run(
            [sudo, "-n", "true"],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _cli_present() -> bool:
    return shutil.which("docker") is not None


def _daemon_ok() -> bool:
    docker = shutil.which("docker")
    if docker is None:
        return False
    try:
        result = subprocess.run(
            [docker, "info"],
            check=False,
            capture_output=True,
            timeout=_PROBE_TIMEOUT_SEC,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _run_install(argv: list[str]) -> bool:
    try:
        result = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=_INSTALL_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        logger.warning("docker install timed out: %s", argv)
        return False
    except OSError as exc:
        logger.warning("docker install failed to start: %s", exc)
        return False
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        logger.warning(
            "docker install exited %s: %s",
            result.returncode,
            stderr[:500] if stderr else "(no stderr)",
        )
        return False
    return True


def _install_argv(manager: str, *, use_sudo: bool) -> list[str] | None:
    prefix: list[str] = []
    if use_sudo:
        sudo = shutil.which("sudo")
        if sudo is None:
            return None
        prefix = [sudo, "-n"]

    # Prefer distro package ``docker.io`` (Ubuntu/Debian) / ``docker`` elsewhere.
    if manager == "apt":
        apt = shutil.which("apt-get") or shutil.which("apt")
        if apt is None:
            return None
        return [
            *prefix,
            "env",
            "DEBIAN_FRONTEND=noninteractive",
            apt,
            "install",
            "-y",
            "-qq",
            "docker.io",
        ]
    if manager == "dnf":
        dnf = shutil.which("dnf")
        return None if dnf is None else [*prefix, dnf, "install", "-y", "docker"]
    if manager == "yum":
        yum = shutil.which("yum")
        return None if yum is None else [*prefix, yum, "install", "-y", "docker"]
    if manager == "pacman":
        pacman = shutil.which("pacman")
        return None if pacman is None else [*prefix, pacman, "-Sy", "--noconfirm", "docker"]
    if manager == "zypper":
        zypper = shutil.which("zypper")
        return None if zypper is None else [*prefix, zypper, "install", "-y", "docker"]
    return None


def _try_auto_install_linux() -> tuple[bool, str]:
    manager = _detect_package_manager()
    if manager is None:
        return False, "no_package_manager"
    if not _can_install_without_password():
        return False, "no_privilege"

    use_sudo = not (hasattr(os, "geteuid") and os.geteuid() == 0)
    if manager == "apt":
        apt = shutil.which("apt-get") or shutil.which("apt")
        if apt is not None:
            update: list[str]
            if use_sudo:
                sudo = shutil.which("sudo")
                if sudo is None:
                    return False, "no_privilege"
                update = [
                    sudo,
                    "-n",
                    "env",
                    "DEBIAN_FRONTEND=noninteractive",
                    apt,
                    "update",
                    "-qq",
                ]
            else:
                update = [
                    "env",
                    "DEBIAN_FRONTEND=noninteractive",
                    apt,
                    "update",
                    "-qq",
                ]
            _run_install(update)

    argv = _install_argv(manager, use_sudo=use_sudo)
    if argv is None:
        return False, "install_failed"
    if not _run_install(argv):
        return False, "install_failed"
    return True, manager


def install_script(
    *,
    plat: str | None = None,
    status: str = "missing",
) -> str:
    """Shell snippet tailored to platform + current Docker status."""
    key = plat or _platform_key()
    if status in {"ready", "installed"}:
        return "# Docker is already usable.\ndocker info\n"

    if status == "daemon_down":
        if key == "darwin":
            return (
                "# docker CLI is present but the daemon is down.\n"
                "# Start Docker Desktop or OrbStack, then verify:\n"
                "open -a Docker 2>/dev/null || open -a OrbStack 2>/dev/null || true\n"
                "# If the app is missing, install one of:\n"
                "#   brew install --cask docker          # Docker Desktop\n"
                "#   brew install --cask orbstack        # OrbStack\n"
                "# Reset a stale context if needed:\n"
                "docker context ls\n"
                "docker context use default 2>/dev/null || true\n"
                "docker info\n"
            )
        if key == "linux":
            return (
                "# docker CLI is present but the daemon is down.\n"
                "sudo systemctl start docker\n"
                "sudo systemctl enable docker\n"
                "docker info\n"
            )
        if key == "win32":
            return (
                "# docker CLI is present but the daemon is down.\n"
                "# Start Docker Desktop from the Start menu, wait until it is idle, then:\n"
                "docker info\n"
            )

    # missing / degraded / skipped → full install
    if key == "linux":
        return (
            "# Install Docker Engine (Linux)\n"
            "curl -fsSL https://get.docker.com | sudo sh\n"
            'sudo usermod -aG docker "$USER"\n'
            "# Log out/in (or newgrp docker), then:\n"
            "docker info\n"
        )
    if key == "darwin":
        return (
            "# macOS — install Docker Desktop\n"
            "brew install --cask docker\n"
            "open -a Docker\n"
            "# Wait until the menu-bar whale is idle, then:\n"
            "docker info\n"
            "# Alternative: brew install --cask orbstack && open -a OrbStack\n"
        )
    if key == "win32":
        return (
            "# Windows — install Docker Desktop\n"
            "# 1. Download: https://docs.docker.com/desktop/setup/install/windows-install/\n"
            "# 2. Run the installer, enable WSL2 if prompted, reboot if asked.\n"
            "# 3. Start Docker Desktop, then in PowerShell:\n"
            "docker info\n"
        )
    return f"# Unsupported platform ({key}). See {_DOCS_BY_PLATFORM.get('linux')}\n"


def agent_prompt(
    *,
    plat: str | None = None,
    status: str = "missing",
) -> str:
    """Natural-language prompt tailored to platform + current Docker status."""
    key = plat or _platform_key()
    host = platform.platform()

    if status in {"ready", "installed"}:
        return f"本机 Docker 已可用（系统：{host}）。请运行 `docker info` 确认，无需再安装。"

    if status == "daemon_down":
        if key == "darwin":
            return (
                "本机已有 docker 命令，但 daemon 未响应。"
                f"当前系统：{host}。"
                "请先检查并启动 Docker Desktop 或 OrbStack（`open -a Docker` / `open -a OrbStack`）；"
                "若应用已卸载，再用 `brew install --cask docker` 或 `brew install --cask orbstack` 重装。"
                "若 `docker context` 指向已不存在的环境（如 orbstack），请切回可用 context 后执行 `docker info` 直到成功。"
            )
        if key == "linux":
            return (
                "本机已有 docker 命令，但 daemon 未响应。"
                f"当前系统：{host}。"
                "请执行 `sudo systemctl start docker`（并视情况 `enable`），"
                "确认当前用户在 `docker` 组后运行 `docker info`。"
            )
        if key == "win32":
            return (
                "本机已有 docker 命令，但 daemon 未响应。"
                f"当前系统：{host}。"
                "请启动 Docker Desktop，等待其就绪后运行 `docker info`。"
            )
        return (
            f"本机已有 docker CLI，但 daemon 未响应（系统：{host}）。"
            "请启动 Docker 服务后验证 `docker info`。"
        )

    if key == "linux":
        return (
            "请在本机帮我安装并启用 Docker Engine，使 `docker info` 可用。"
            f"当前系统：{host}。"
            "优先用官方脚本 `curl -fsSL https://get.docker.com | sudo sh`，"
            "并把当前用户加入 `docker` 组；完成后验证 `docker info`。"
            "如需 sudo 密码请提示我手动输入，不要把密钥写进命令历史。"
        )
    if key == "darwin":
        return (
            "请帮我在 macOS 上安装 Docker Desktop（可用 `brew install --cask docker`），"
            "并引导我打开 Docker.app，直到 `docker info` 成功。"
            f"当前系统：{host}。"
        )
    if key == "win32":
        return (
            "请指导我在 Windows 上安装 Docker Desktop（含 WSL2 如需要），"
            "并确认安装后 `docker info` 可用。"
            f"当前系统：{host}。"
        )
    return (
        f"请帮我在当前系统（{host}）安装 Docker，并验证 `docker info` 可用。"
        f"参考文档：{_DOCS_BY_PLATFORM.get('linux')}"
    )


def docker_status(*, attempt_install: bool = False) -> dict[str, Any]:
    """Return Docker environment status (+ optional best-effort install on Linux)."""
    plat = _platform_key()
    docs = _DOCS_BY_PLATFORM.get(plat, _DOCS_BY_PLATFORM["linux"])

    cli = _cli_present()
    daemon = _daemon_ok() if cli else False

    if cli and daemon:
        status = "ready"
        reason = "already_present"
        detail = ""
    elif cli and not daemon:
        status = "daemon_down"
        reason = "daemon_unreachable"
        detail = "docker CLI found but daemon not responding (start Docker Desktop / dockerd)"
    elif not attempt_install:
        status = "missing"
        reason = "not_installed"
        detail = "docker CLI not found on PATH"
    elif plat != "linux":
        status = "skipped"
        reason = "manual_install_required"
        detail = f"auto-install is Linux-only; use install_script or docs for {plat}"
    else:
        ok, install_reason = _try_auto_install_linux()
        if not ok:
            status = "degraded"
            reason = install_reason
            detail = f"could not auto-install docker ({install_reason})"
            cli = _cli_present()
            daemon = _daemon_ok() if cli else False
        else:
            cli = _cli_present()
            daemon = _daemon_ok() if cli else False
            if cli and daemon:
                status = "installed"
                reason = "install_ok"
                detail = f"installed via {install_reason}"
            elif cli:
                status = "daemon_down"
                reason = "installed_daemon_down"
                detail = "docker package installed but daemon not running; start the service"
            else:
                status = "degraded"
                reason = "install_failed"
                detail = "package manager reported success but docker CLI still missing"

    can_auto = (
        plat == "linux"
        and _detect_package_manager() is not None
        and _can_install_without_password()
        and status not in {"ready", "installed"}
    )

    return {
        "platform": plat,
        "cli": cli,
        "daemon": daemon,
        "docs_url": docs,
        "install_script": install_script(plat=plat, status=status),
        "agent_prompt": agent_prompt(plat=plat, status=status),
        "can_auto_install": can_auto,
        "status": status,
        "reason": reason,
        "detail": detail,
    }


def ensure_docker() -> dict[str, Any]:
    """Best-effort ensure Docker is usable (detect + optional Linux auto-install)."""
    return docker_status(attempt_install=True)


__all__ = [
    "agent_prompt",
    "docker_status",
    "ensure_docker",
    "install_script",
]
