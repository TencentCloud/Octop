"""Self-upgrade helpers shared by CLI and HTTP update API."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from octop.infra.utils.paths import PathLayout

logger = logging.getLogger(__name__)

_PACKAGE_NAME = "octop"
_PYPI_URL = f"https://pypi.org/pypi/{_PACKAGE_NAME}/json"

_MIRRORS = [
    "https://mirrors.cloud.tencent.com/pypi/simple",
    "https://mirrors.aliyun.com/pypi/simple",
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    "https://mirrors.ustc.edu.cn/pypi/simple",
]

_COMMON_UV_PATHS = [
    os.path.expanduser("~/.local/bin/uv"),
    os.path.expanduser("~/.cargo/bin/uv"),
    "/usr/local/bin/uv",
    "/opt/homebrew/bin/uv",
]


@dataclass
class UpgradeResult:
    success: bool
    message: str | None = None
    error: str | None = None
    installed_version: str | None = None
    mirror_errors: list[str] = field(default_factory=list)


def resolve_venv_python() -> str:
    """Return the Python executable for the managed ~/.octop/venv install."""
    base_prefix = getattr(sys, "base_prefix", sys.prefix)
    if sys.prefix != base_prefix:
        return sys.executable

    virtual_env = os.environ.get("VIRTUAL_ENV", "").strip()
    if virtual_env:
        for rel in ("bin/python", "Scripts/python.exe"):
            candidate = Path(virtual_env) / rel
            if candidate.is_file():
                return str(candidate)

    for rel in ("bin/python", "Scripts/python.exe"):
        candidate = PathLayout.from_env().root / "venv" / rel
        if candidate.is_file():
            return str(candidate)

    return sys.executable


def detect_installer() -> str:
    if shutil.which("uv"):
        return "uv"
    for candidate in _COMMON_UV_PATHS:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return "uv"
    return "pip"


def find_uv_executable() -> str:
    if shutil.which("uv"):
        return "uv"
    for candidate in _COMMON_UV_PATHS:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return "uv"


def get_local_version() -> str:
    try:
        from importlib.metadata import version

        return version(_PACKAGE_NAME)
    except Exception:
        return "0.0.0"


def fetch_latest_pypi_version(timeout: int = 10) -> str | None:
    info = fetch_pypi_info(timeout=timeout)
    return info.version if info else None


@dataclass
class PyPIInfo:
    version: str
    description: str | None = None


def fetch_pypi_info(timeout: int = 10) -> PyPIInfo | None:
    """Fetch version and long description from the PyPI JSON API.

    Returns None on any network or parse failure.
    """
    try:
        req = urllib.request.Request(
            _PYPI_URL,
            headers={"User-Agent": f"{_PACKAGE_NAME}-updater/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        info = data["info"]
        return PyPIInfo(
            version=str(info["version"]),
            description=info.get("description"),
        )
    except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
        logger.warning("failed to fetch PyPI info: %s", exc)
        return None


def parse_changelog_for_version(description: str | None, version: str) -> str | None:
    """Extract the changelog entry for *version* from a Keep a Changelog string.

    Searches for ``## [<version>]`` and returns everything up to the next
    ``## [`` heading (or end of string). Returns None if not found.
    """
    if not description:
        return None
    pattern = re.compile(
        r"(##\s+\[" + re.escape(version) + r"\][^\n]*\n.*?)(?=\n##\s+\[|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(description)
    if not match:
        return None
    return match.group(1).strip()


def parse_version(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for segment in value.split("."):
        numeric = ""
        for ch in segment:
            if ch.isdigit():
                numeric += ch
            else:
                break
        parts.append(int(numeric) if numeric else 0)
    return tuple(parts)


def is_newer(remote: str, local: str) -> bool:
    return parse_version(remote) > parse_version(local)


def get_editable_path() -> str | None:
    try:
        import importlib.metadata as meta

        dist = meta.distribution(_PACKAGE_NAME)
        direct_url = dist.read_text("direct_url.json")
        if direct_url:
            info = json.loads(direct_url)
            if info.get("dir_info", {}).get("editable", False):
                return info.get("url", "").replace("file://", "") or None
    except Exception:
        pass
    return None


def has_pip(python_exe: str) -> bool:
    try:
        result = subprocess.run(
            [python_exe, "-m", "pip", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def find_pip_in_venv(python_exe: str) -> str | None:
    bin_dir = os.path.dirname(os.path.abspath(python_exe))
    for name in ("pip", "pip3"):
        candidate = os.path.join(bin_dir, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def build_upgrade_command(
    installer: str,
    venv_python: str,
    *,
    index_url: str = "",
) -> list[str] | None:
    if installer == "uv":
        uv_exe = find_uv_executable()
        cmd = [
            uv_exe,
            "pip",
            "install",
            "--python",
            venv_python,
            "--upgrade-package",
            _PACKAGE_NAME,
        ]
        if index_url:
            cmd.extend(["--index-url", index_url])
        cmd.append(_PACKAGE_NAME)
        return cmd

    upgrade_flags = ["--upgrade", "--upgrade-strategy", "only-if-needed"]
    if has_pip(venv_python):
        cmd = [venv_python, "-m", "pip", "install", *upgrade_flags]
    else:
        venv_pip = find_pip_in_venv(venv_python)
        if venv_pip:
            cmd = [venv_pip, "install", *upgrade_flags]
        else:
            standalone = shutil.which("pip3") or shutil.which("pip")
            if not standalone:
                return None
            cmd = [standalone, "install", *upgrade_flags]
    if index_url:
        cmd.extend(["-i", index_url])
    cmd.append(_PACKAGE_NAME)
    return cmd


def get_installed_version(python_exe: str) -> str | None:
    try:
        result = subprocess.run(
            [
                python_exe,
                "-c",
                f"from importlib.metadata import version; print(version({_PACKAGE_NAME!r}))",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        pass
    return None


def run_upgrade(*, verbose: bool = False) -> UpgradeResult:
    # [FPK guard] FnOS FPK 部署下禁止内置在线升级：运行时从应用中心托管的
    # 打包 site-packages 加载（launcher 设置 PYTHONPATH），在线安装到系统
    # Python 永远无法生效，重启后仍加载旧版；升级请通过飞牛应用中心安装
    # 新版 FPK。launcher / docker-compose 设置 OCTOP_INSTALL_MODE=fpk-*
    # 触发本分支。
    _fpk_mode = os.environ.get("OCTOP_INSTALL_MODE", "").lower()
    if _fpk_mode.startswith("fpk"):
        return UpgradeResult(
            success=False,
            error=(
                "当前为飞牛 FPK 安装，内置在线升级不适用于本部署方式；"
                "请在飞牛应用中心检查并安装新版 FPK 完成升级。"
            ),
        )
    installer = detect_installer()
    venv_python = resolve_venv_python()
    local_ver = get_local_version()
    mirror_errors: list[str] = []
    per_mirror_timeout = 180

    def _run_install(cmd: list[str], label: str) -> tuple[int | None, str]:
        logger.debug("running %s: %s", label, " ".join(cmd))
        try:
            # NOCA:DangerousSubprocessUseAudit(argv list with shell=False; installer paths and mirrors are trusted)
            result = subprocess.run(
                cmd,
                check=False,
                capture_output=not verbose,
                text=True,
                timeout=per_mirror_timeout,
            )
        except subprocess.TimeoutExpired:
            return None, f"timed out after {per_mirror_timeout}s"
        if result.returncode == 0:
            return 0, ""
        snippet = (result.stderr or result.stdout or "")[:300]
        return result.returncode, snippet

    for mirror in _MIRRORS:
        cmd = build_upgrade_command(installer, venv_python, index_url=mirror)
        if cmd is None:
            return UpgradeResult(
                success=False,
                error="pip is not available for the Octop virtual environment.",
                mirror_errors=mirror_errors,
            )
        rc, err_snippet = _run_install(cmd, mirror)
        if rc == 0:
            return _verify_upgrade(local_ver, venv_python, mirror_errors)
        mirror_errors.append(f"{mirror}: {err_snippet}")

    cmd = build_upgrade_command(installer, venv_python)
    if cmd is None:
        return UpgradeResult(
            success=False,
            error="pip is not available for the Octop virtual environment.",
            mirror_errors=mirror_errors,
        )
    rc, err_snippet = _run_install(cmd, "pypi.org")
    if rc != 0:
        mirror_errors.append(f"pypi.org: {err_snippet or 'unknown error'}")
        return UpgradeResult(
            success=False,
            error="upgrade failed on all mirrors",
            mirror_errors=mirror_errors,
        )
    return _verify_upgrade(local_ver, venv_python, mirror_errors)


def _verify_upgrade(
    local_ver: str,
    venv_python: str,
    mirror_errors: list[str],
) -> UpgradeResult:
    actual_ver: str | None = None
    for attempt in range(3):
        actual_ver = get_installed_version(venv_python)
        if actual_ver and actual_ver != local_ver:
            break
        if attempt < 2:
            time.sleep(0.5)

    if actual_ver and is_newer(actual_ver, local_ver):
        return UpgradeResult(
            success=True,
            message=f"upgraded to {actual_ver}",
            installed_version=actual_ver,
            mirror_errors=mirror_errors,
        )
    if actual_ver == local_ver:
        return UpgradeResult(
            success=True,
            message=f"installer finished but version is still {actual_ver}",
            installed_version=actual_ver,
            mirror_errors=mirror_errors,
        )
    return UpgradeResult(
        success=True,
        message="upgrade completed",
        installed_version=actual_ver,
        mirror_errors=mirror_errors,
    )
