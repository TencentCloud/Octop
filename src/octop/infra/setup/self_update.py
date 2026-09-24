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
from typing import Any

from octop.infra.utils.paths import PathLayout

logger = logging.getLogger(__name__)

_PACKAGE_NAME = "octop"
_PYPI_URL = f"https://pypi.org/pypi/{_PACKAGE_NAME}/json"
_GREEN_PACKAGES_ENV = "OCTOP_GREEN_PACKAGES"
_STASH_SUFFIX = ".octop-old"

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


def green_packages_dir() -> Path | None:
    """Return ``--target`` dir for green portable installs, if configured."""
    raw = (os.environ.get(_GREEN_PACKAGES_ENV) or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def resolve_venv_python() -> str:
    """Return the Python executable for the managed ~/.octop/venv install."""
    # Green portable: always the interpreter that launched launch.py, never ~/.octop/venv.
    if green_packages_dir() is not None:
        return sys.executable

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


@dataclass
class PyPIInfo:
    version: str
    """Newest version on the index, including pre-releases (``latest_any``)."""

    description: str | None = None
    """Package long description."""

    source: str | None = None
    """Label of the source that served this payload (e.g. ``pypi.org``)."""

    latest_stable: str | None = None
    """Newest non-pre-release version, or None if every release is a pre-release."""


def fetch_latest_pypi_version(
    timeout: int = 10,
    *,
    include_prerelease: bool = False,
) -> str | None:
    info = fetch_pypi_info(timeout=timeout)
    if info is None:
        return None
    if include_prerelease:
        return info.version
    return info.latest_stable


def _usable_release_versions(data: dict[str, Any]) -> list[str]:
    """Return PyPI ``releases`` keys that are not fully yanked."""
    releases = data.get("releases")
    if not isinstance(releases, dict):
        return []
    versions: list[str] = []
    for raw_ver, files in releases.items():
        ver = str(raw_ver)
        if not ver:
            continue
        if (
            isinstance(files, list)
            and files
            and all(isinstance(item, dict) and item.get("yanked") for item in files)
        ):
            continue
        versions.append(ver)
    return versions


def pick_latest_versions(versions: list[str]) -> tuple[str | None, str | None]:
    """Return ``(latest_any, latest_stable)`` using PEP 440 order."""
    usable = [ver for ver in versions if ver]
    if not usable:
        return None, None
    latest_any = max(usable, key=parse_version)
    stables = [ver for ver in usable if not is_prerelease(ver)]
    latest_stable = max(stables, key=parse_version) if stables else None
    return latest_any, latest_stable


def fetch_pypi_info(timeout: int = 10) -> PyPIInfo | None:
    """Fetch version and long description from the PyPI JSON API.

    ``version`` is the newest release including pre-releases. ``latest_stable``
    is the newest non-pre-release (None when the index only has pre-releases).
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
        versions = _usable_release_versions(data)
        info_version = str(info["version"])
        if info_version and info_version not in versions:
            versions.append(info_version)
        latest_any, latest_stable = pick_latest_versions(versions)
        if latest_any is None:
            latest_any = info_version
            latest_stable = info_version if not is_prerelease(info_version) else None
        return PyPIInfo(
            version=latest_any,
            latest_stable=latest_stable,
            description=info.get("description"),
            source="pypi.org",
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


# PEP 440 letter ranks: a/alpha < b/beta < rc/c/pre/preview. Final has no pre.
_PRE_RANK = {
    "a": 0,
    "alpha": 0,
    "b": 1,
    "beta": 1,
    "c": 2,
    "rc": 2,
    "pre": 2,
    "preview": 2,
}

_PEP440_RE = re.compile(
    r"""
    ^v?
    (?:(?P<epoch>\d+)!)?
    (?P<release>\d+(?:\.\d+)*)
    (?:
        [-_\.]?
        (?P<pre_l>alpha|a|beta|b|preview|pre|rc|c)
        [-_\.]?
        (?P<pre_n>\d+)?
    )?
    (?:
        (?:[-_\.]?(?P<post_l>post|rev|r)[-_\.]?(?P<post_n>\d+))
        |
        (?:-(?P<post_n1>\d+))
    )?
    (?:
        [-_\.]?
        (?P<dev_l>dev)
        [-_\.]?
        (?P<dev_n>\d+)?
    )?
    (?:\+(?P<local>[a-z0-9]+(?:[-_\.][a-z0-9]+)*))?
    $
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _numeric_release_key(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for segment in value.split("."):
        numeric = ""
        for ch in segment:
            if ch.isdigit():
                numeric += ch
            else:
                break
        parts.append(int(numeric) if numeric else 0)
    return tuple(parts) or (0,)


VersionKey = tuple[int, tuple[int, ...], tuple[int, ...], int, tuple[int, ...]]


def parse_version(value: str) -> VersionKey:
    """Return a comparable PEP 440 sort key for *value*."""
    match = _PEP440_RE.match(value.strip())
    if match is None:
        # Unknown shape: keep previous numeric-only behaviour.
        numeric = _numeric_release_key(value)
        return (0, numeric + (0,) * max(0, 8 - len(numeric)), (1,), -1, (1,))
    epoch = int(match.group("epoch") or 0)
    release_parts = tuple(int(part) for part in match.group("release").split("."))
    # Pad so 1.0 and 1.0.0 compare equal under tuple ordering.
    release = release_parts + (0,) * max(0, 8 - len(release_parts))
    pre_l = match.group("pre_l")
    if pre_l:
        pre_key: tuple[int, ...] = (
            0,
            _PRE_RANK[pre_l.lower()],
            int(match.group("pre_n") or 0),
        )
    elif match.group("dev_l"):
        # Bare .devN sorts before a/b/rc of the same release.
        pre_key = (-1,)
    else:
        pre_key = (1,)
    post_raw = match.group("post_n") or match.group("post_n1")
    post_key = int(post_raw) if post_raw is not None else -1
    if match.group("dev_l"):
        dev_key: tuple[int, ...] = (0, int(match.group("dev_n") or 0))
    else:
        dev_key = (1,)
    return (epoch, release, pre_key, post_key, dev_key)


def is_prerelease(value: str) -> bool:
    """True when *value* is a PEP 440 pre-release (a/b/rc/dev)."""
    match = _PEP440_RE.match(value.strip())
    if match is None:
        return False
    return match.group("pre_l") is not None or match.group("dev_l") is not None


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


def package_requirement(version: str | None = None) -> str:
    """Return ``octop`` or a pinned ``octop==<version>`` spec."""
    if version:
        return f"{_PACKAGE_NAME}=={version}"
    return _PACKAGE_NAME


def append_prerelease_flags(
    cmd: list[str],
    installer: str,
    *,
    allow_prerelease: bool,
) -> None:
    if not allow_prerelease:
        return
    if installer == "uv":
        cmd.extend(["--prerelease", "allow"])
    else:
        cmd.append("--pre")


def build_upgrade_command(
    installer: str,
    venv_python: str,
    *,
    index_url: str = "",
    allow_prerelease: bool = False,
    version: str | None = None,
) -> list[str] | None:
    target = green_packages_dir()
    target_args: list[str] = []
    if target is not None:
        target_args = ["--target", str(target)]
    requirement = package_requirement(version)

    if installer == "uv":
        uv_exe = find_uv_executable()
        cmd = [
            uv_exe,
            "pip",
            "install",
            "--python",
            venv_python,
            *target_args,
            "--upgrade-package",
            _PACKAGE_NAME,
        ]
        if index_url:
            cmd.extend(["--index-url", index_url])
        append_prerelease_flags(cmd, installer, allow_prerelease=allow_prerelease)
        cmd.append(requirement)
        return cmd

    upgrade_flags = ["--upgrade", "--upgrade-strategy", "only-if-needed"]
    if has_pip(venv_python):
        cmd = [venv_python, "-m", "pip", "install", *upgrade_flags, *target_args]
    else:
        venv_pip = find_pip_in_venv(venv_python)
        if venv_pip:
            cmd = [venv_pip, "install", *upgrade_flags, *target_args]
        else:
            standalone = shutil.which("pip3") or shutil.which("pip")
            if not standalone:
                return None
            cmd = [standalone, "install", *upgrade_flags, *target_args]
    if index_url:
        cmd.extend(["-i", index_url])
    append_prerelease_flags(cmd, installer, allow_prerelease=allow_prerelease)
    cmd.append(requirement)
    return cmd


def _is_windows() -> bool:
    return os.name == "nt"


def stash_console_scripts(python_exe: str) -> list[tuple[Path, Path]]:
    """Rename the ``octop`` launchers next to *python_exe* out of the way.

    Windows refuses to delete or overwrite the executable backing a running
    process (``os error 32``), which makes pip and uv fail while rewriting
    ``Scripts/octop.exe`` during ``octop update``. Renaming the file is still
    permitted, so the installer gets a free path and the running process keeps
    its handle. Returns the ``(original, stash)`` pairs that were moved.
    """
    if not _is_windows():
        return []
    script_dir = Path(python_exe).parent
    _purge_stale_stashes(script_dir)
    moved: list[tuple[Path, Path]] = []
    for script in sorted(script_dir.glob(f"{_PACKAGE_NAME}*.exe")):
        stash = script.with_name(script.name + _STASH_SUFFIX)
        try:
            script.replace(stash)
        except OSError as exc:
            logger.warning("could not move %s aside: %s", script, exc)
            continue
        moved.append((script, stash))
    return moved


def restore_console_scripts(moved: list[tuple[Path, Path]]) -> None:
    """Put stashed launchers back after a failed upgrade."""
    for original, stash in moved:
        if original.exists() or not stash.exists():
            continue
        try:
            stash.replace(original)
        except OSError as exc:
            logger.warning("could not restore %s: %s", original, exc)


def discard_console_script_stashes(moved: list[tuple[Path, Path]]) -> None:
    """Drop stashes after a successful upgrade, ignoring still-locked files."""
    for _original, stash in moved:
        _unlink_quietly(stash)


def _purge_stale_stashes(script_dir: Path) -> None:
    for stale in script_dir.glob(f"*{_STASH_SUFFIX}"):
        _unlink_quietly(stale)


def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        # Still held by the running process — the next upgrade purges it.
        logger.debug("could not remove %s: %s", path, exc)


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


def get_version_in_dir(python_exe: str, target: str) -> str | None:
    """Return the octop version installed in *target* (a ``pip --target`` dir)."""
    try:
        code = (
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "from importlib.metadata import version; print(version('octop'))"
        )
        result = subprocess.run(
            [python_exe, "-c", code, target],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        pass
    return None


def _verify_fpk_upgrade(
    local_ver: str,
    site_packages: str,
    python_exe: str,
    mirror_errors: list[str],
) -> UpgradeResult:
    actual_ver: str | None = None
    for attempt in range(3):
        actual_ver = get_version_in_dir(python_exe, site_packages)
        if actual_ver and actual_ver != local_ver:
            break
        if attempt < 2:
            time.sleep(0.5)

    if actual_ver and is_newer(actual_ver, local_ver):
        return UpgradeResult(
            success=True,
            message=f"已升级到 {actual_ver}，请重启服务生效（应用中心托管的服务重启后加载新版）。",
            installed_version=actual_ver,
            mirror_errors=mirror_errors,
        )
    if actual_ver == local_ver:
        return UpgradeResult(
            success=False,
            error=(
                f"安装完成但版本仍为 {actual_ver}；"
                "请确认新版已发布，或改用飞牛应用中心安装新版 FPK。"
            ),
            installed_version=actual_ver,
            mirror_errors=mirror_errors,
        )
    return UpgradeResult(
        success=True,
        message="upgrade completed",
        installed_version=actual_ver,
        mirror_errors=mirror_errors,
    )


def _run_fpk_upgrade(
    site_packages: str,
    *,
    verbose: bool = False,
    allow_prerelease: bool = False,
    version: str | None = None,
) -> UpgradeResult:
    """FnOS FPK 部署下的在线升级：把新版安装到 launcher 实际加载的打包目录。

    launcher 通过 PYTHONPATH 从应用中心托管的打包 site-packages 加载 octop，
    在线安装到系统 Python 永远不会被加载（重启后仍是旧版）。本函数把新版
    安装到该打包目录本身，重启服务后即加载新版，升级真正生效。

    与普通部署不同，FPK 首次在线升级需要从零解析并下载完整依赖树
    （octop 依赖 orcakit-harness-agent 等大包），故超时显著放宽；且某镜像
    可能滞后（装到同版本旧版），此时继续尝试下一个镜像，最后以 pypi.org
    兜底，避免「镜像有货但版本不新」导致升级假成功。
    """
    if not os.path.isdir(site_packages):
        return UpgradeResult(
            success=False,
            error=f"FPK site-packages 目录不存在：{site_packages}",
        )
    local_ver = get_local_version()
    mirror_errors: list[str] = []
    per_mirror_timeout = 900  # FPK 首次升级需下载完整依赖树，180s 不够

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

    python_exe = sys.executable
    installer = detect_installer()  # uv 优先：pip 对 orcakit-harness-agent[all] 依赖树解析会卡死

    def _build_cmd(index_url: str = "") -> list[str]:
        requirement = package_requirement(version)
        if installer == "uv":
            cmd = [
                find_uv_executable(),
                "pip",
                "install",
                "--python",
                python_exe,
                "--target",
                site_packages,
                "--upgrade-package",
                _PACKAGE_NAME,
            ]
            if index_url:
                cmd.extend(["--index-url", index_url])
            append_prerelease_flags(cmd, installer, allow_prerelease=allow_prerelease)
            cmd.append(requirement)
            return cmd
        cmd = [
            python_exe,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--upgrade-strategy",
            "only-if-needed",
            "--target",
            site_packages,
        ]
        if index_url:
            cmd.extend(["-i", index_url])
        append_prerelease_flags(cmd, installer, allow_prerelease=allow_prerelease)
        cmd.append(requirement)
        return cmd

    for mirror in _MIRRORS:
        rc, err_snippet = _run_install(_build_cmd(mirror), mirror)
        if rc != 0:
            mirror_errors.append(f"{mirror}: {err_snippet}")
            continue
        res = _verify_fpk_upgrade(local_ver, site_packages, python_exe, mirror_errors)
        if res.success:
            return res
        # 镜像装到了同版本/旧版（同步滞后）：继续尝试下一个镜像
        mirror_errors.append(f"{mirror}: {res.error or 'version unchanged'}")

    rc, err_snippet = _run_install(_build_cmd(), "pypi.org")
    if rc != 0:
        mirror_errors.append(f"pypi.org: {err_snippet or 'unknown error'}")
        return UpgradeResult(
            success=False,
            error="upgrade failed on all mirrors",
            mirror_errors=mirror_errors,
        )
    return _verify_fpk_upgrade(local_ver, site_packages, python_exe, mirror_errors)


def run_upgrade(
    *,
    verbose: bool = False,
    allow_prerelease: bool = False,
    version: str | None = None,
) -> UpgradeResult:
    # [FPK] FnOS FPK 部署：launcher 通过 PYTHONPATH 从应用中心托管的打包
    # site-packages 加载 octop，在线安装到系统 Python 永远不会被加载（重启
    # 无效）。launcher 导出 OCTOP_FPK_SITE_PACKAGES 指向该打包目录，升级即
    # 安装到此目录并提示重启服务生效——升级真正可用，而非禁止升级。
    _fpk_site = os.environ.get("OCTOP_FPK_SITE_PACKAGES", "").strip()
    if _fpk_site:
        return _run_fpk_upgrade(
            _fpk_site,
            verbose=verbose,
            allow_prerelease=allow_prerelease,
            version=version,
        )

    # Windows keeps the running octop.exe locked (os error 32), so pip / uv
    # cannot rewrite the console script. Renaming it is still allowed, so move
    # the launchers aside first and restore them if the upgrade fails.
    stashed = stash_console_scripts(resolve_venv_python())
    try:
        result = _run_managed_upgrade(
            verbose=verbose,
            allow_prerelease=allow_prerelease,
            version=version,
        )
    except BaseException:
        restore_console_scripts(stashed)
        raise
    if result.success:
        discard_console_script_stashes(stashed)
    else:
        restore_console_scripts(stashed)
    return result


def _run_managed_upgrade(
    *,
    verbose: bool = False,
    allow_prerelease: bool = False,
    version: str | None = None,
) -> UpgradeResult:
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
        cmd = build_upgrade_command(
            installer,
            venv_python,
            index_url=mirror,
            allow_prerelease=allow_prerelease,
            version=version,
        )
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

    cmd = build_upgrade_command(
        installer,
        venv_python,
        allow_prerelease=allow_prerelease,
        version=version,
    )
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
