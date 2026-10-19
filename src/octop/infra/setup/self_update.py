"""Self-upgrade helpers shared by CLI and HTTP update API."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from email.parser import BytesParser
from pathlib import Path
from typing import Any

from octop.i18n import lookup, tr
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.locale import DEFAULT_LOCALE
from octop.infra.utils.paths import PathLayout

logger = logging.getLogger(__name__)

_PACKAGE_NAME = "octop"
_PYPI_URL = f"https://pypi.org/pypi/{_PACKAGE_NAME}/json"
_PYPI_SIMPLE = "https://pypi.org/simple"
_PYPI_UA = {"User-Agent": f"{_PACKAGE_NAME}-updater/1.0"}
_GREEN_PACKAGES_ENV = "OCTOP_GREEN_PACKAGES"
_STASH_SUFFIX = ".octop-old"
_PROBE_TIMEOUT_S = 8
_PROBE_PREFIX = "__OCTOP_PROBE__"
_INSTALL_TIMEOUT_S = 90
_TARGET_INSTALL_TIMEOUT_S = 900

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


@dataclass(frozen=True)
class IndexProbe:
    """Result of probing a PEP 503 simple index for ``octop``."""

    index_url: str
    label: str
    elapsed: float
    status: str  # has_version | missing_version | unreachable
    detail: str = ""


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


def _bundled_uv_executable() -> str | None:
    target = green_packages_dir()
    if target is None:
        return None
    candidate = target / "bin" / ("uv.exe" if os.name == "nt" else "uv")
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return str(candidate)
    return None


def detect_installer() -> str:
    if _bundled_uv_executable() is not None:
        return "uv"
    if shutil.which("uv"):
        return "uv"
    for candidate in _COMMON_UV_PATHS:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return "uv"
    return "pip"


def find_uv_executable() -> str:
    bundled = _bundled_uv_executable()
    if bundled is not None:
        return bundled
    if shutil.which("uv"):
        return "uv"
    for candidate in _COMMON_UV_PATHS:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return "uv"


def get_local_version() -> str:
    try:
        from importlib.metadata import version

        target = green_packages_dir()
        fpk_target = os.environ.get("OCTOP_FPK_SITE_PACKAGES", "").strip()
        if target is not None or fpk_target:
            return get_version_in_dir(sys.executable, str(target or fpk_target)) or "0.0.0"
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


def _pypi_json_url(version: str | None = None) -> str:
    if not version:
        return _PYPI_URL
    encoded = urllib.parse.quote(version, safe="")
    return f"https://pypi.org/pypi/{_PACKAGE_NAME}/{encoded}/json"


def _load_pypi_json(url: str, timeout: int) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=_PYPI_UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
    return payload


def _description_for_version(
    version: str,
    fallback: str | None,
    timeout: int,
) -> str | None:
    """Return the long description uploaded with *version*.

    Warehouse's unversioned ``/pypi/<name>/json`` ``info`` object is the latest
    *stable* release. Pre-release changelogs only appear on
    ``/pypi/<name>/<version>/json``.
    """
    try:
        data = _load_pypi_json(_pypi_json_url(version), timeout)
        description = data["info"].get("description")
        if isinstance(description, str) and description.strip():
            return description
    except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
        logger.warning("failed to fetch PyPI description for %s: %s", version, exc)
    return fallback


def fetch_pypi_info(timeout: int = 10) -> PyPIInfo | None:
    """Fetch version and long description from the PyPI JSON API.

    ``version`` is the newest release including pre-releases. ``latest_stable``
    is the newest non-pre-release (None when the index only has pre-releases).
    Returns None on any network or parse failure.
    """
    try:
        data = _load_pypi_json(_PYPI_URL, timeout)
        info = data["info"]
        versions = _usable_release_versions(data)
        info_version = str(info["version"])
        if info_version and info_version not in versions:
            versions.append(info_version)
        latest_any, latest_stable = pick_latest_versions(versions)
        if latest_any is None:
            latest_any = info_version
            latest_stable = info_version if not is_prerelease(info_version) else None
        raw_description = info.get("description")
        description = raw_description if isinstance(raw_description, str) else None
        if latest_any and latest_any != info_version:
            description = _description_for_version(latest_any, description, timeout)
        return PyPIInfo(
            version=latest_any,
            latest_stable=latest_stable,
            description=description,
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


def validate_upgrade_target(version: str | None, local_ver: str) -> None:
    """Reject reinstalls/downgrades before any installer changes the environment."""
    if version is not None and not is_newer(version, local_ver):
        raise OctopError(
            ErrorCode.UPDATE_TARGET_NOT_NEWER,
            tr("errors.UPDATE_TARGET_NOT_NEWER", "en", target=version, current=local_ver),
            details={"target": version, "current": local_ver},
        )


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


def get_version_in_dir(python_exe: str, target: str, *, check_cli: bool = False) -> str | None:
    """Read the loaded target version, optionally exercising its CLI entry point."""
    try:
        code = (
            "import json, site, sys; from pathlib import Path; "
            "target = Path(sys.argv[1]).resolve(); "
            "sys.path.insert(0, str(target)); site.addsitedir(str(target)); "
            "import octop; "
            "actual = octop.__version__ if "
            "Path(octop.__file__).resolve().is_relative_to(target) else None\n"
            "if actual is not None and sys.argv[2] == '1':\n"
            " import contextlib, io, runpy\n"
            " sys.argv = ['octop', '--version']\n"
            " with contextlib.redirect_stdout(io.StringIO()):\n"
            "  try:\n"
            "   runpy.run_module('octop', run_name='__main__', alter_sys=True)\n"
            "  except SystemExit as exc:\n"
            "   if exc.code not in (None, 0): raise\n"
            f"print('\\n{_PROBE_PREFIX}' + json.dumps(actual))"
        )
        result = subprocess.run(
            [python_exe, "-B", "-c", code, target, "1" if check_cli else "0"],
            capture_output=True,
            text=True,
            check=False,
            timeout=_PROBE_TIMEOUT_S,
        )
        if result.returncode == 0:
            payloads = [
                line.removeprefix(_PROBE_PREFIX)
                for line in result.stdout.splitlines()
                if line.startswith(_PROBE_PREFIX)
            ]
            if len(payloads) != 1:
                return None
            loaded_version = json.loads(payloads[0])
            return loaded_version if isinstance(loaded_version, str) and loaded_version else None
    except Exception:
        pass
    return None


def _target_dependencies_satisfied(
    target: Path, wheel: Path, *, version: str | None = None
) -> bool:
    """Check a downloaded wheel's dependency closure before modifying the target."""
    try:
        from importlib.metadata import Distribution, distributions

        from packaging.requirements import Requirement
        from packaging.specifiers import SpecifierSet
        from packaging.utils import canonicalize_name
        from packaging.version import Version

        with zipfile.ZipFile(wheel) as archive:
            records = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(records) != 1:
                return False
            release = BytesParser().parsebytes(archive.read(records[0]))
        if (
            len(release.get_all("Name", [])) != 1
            or len(release.get_all("Version", [])) != 1
            or canonicalize_name(release.get("Name", "")) != _PACKAGE_NAME
        ):
            return False
        actual_version = Version(release.get("Version", ""))
        if version is not None and actual_version != Version(version):
            return False

        installed: dict[str, list[Distribution]] = {}
        for dist in distributions(path=[str(target)]):
            name = canonicalize_name(dist.metadata.get("Name", ""))
            installed.setdefault(name, []).append(dist)
        seen: set[tuple[str, frozenset[str]]] = set()

        def satisfied(
            name: str,
            requirements: list[str],
            python_required: str | None,
            extras: frozenset[str],
        ) -> bool:
            key = (name, extras)
            if key in seen:
                return True
            seen.add(key)
            # The portable path uses sys.executable, so this is the target's Python.
            if python_required and not SpecifierSet(python_required).contains(
                ".".join(map(str, sys.version_info[:3])), prereleases=True
            ):
                return False
            for raw in requirements:
                requirement = Requirement(raw)
                if requirement.marker and not any(
                    requirement.marker.evaluate({"extra": extra}) for extra in {"", *extras}
                ):
                    continue
                candidates = installed.get(canonicalize_name(requirement.name), [])
                # Ambiguous metadata or direct URLs cannot establish a safe fast path.
                if requirement.url or len(candidates) != 1:
                    return False
                dependency = candidates[0]
                if not requirement.specifier.contains(dependency.version, prereleases=True):
                    return False
                if not satisfied(
                    canonicalize_name(requirement.name),
                    dependency.requires or [],
                    dependency.metadata.get("Requires-Python"),
                    frozenset(requirement.extras),
                ):
                    return False
            return True

        return satisfied(
            _PACKAGE_NAME,
            release.get_all("Requires-Dist", []),
            release.get("Requires-Python"),
            frozenset(),
        )
    except Exception:
        # Missing packaging, malformed metadata, or unreadable records require resolution.
        return False


def index_label(index_url: str) -> str:
    """Short label for logs / UI (hostname, or ``pypi.org``)."""
    host = urllib.parse.urlparse(index_url).hostname
    if host == "pypi.org":
        return "pypi.org"
    return host or index_url


def _index_package_url(index_url: str) -> str:
    return f"{index_url.rstrip('/')}/{_PACKAGE_NAME}/"


def page_has_package_version(body: str, version: str | None) -> bool:
    """True when a PEP 503 simple page lists *version* (or any file when unpinned)."""
    if not version:
        return bool(body.strip())
    # Wheel / sdist names: octop-1.0.1-py3-none-any.whl, octop-1.0.1.tar.gz
    return f"{_PACKAGE_NAME}-{version}-" in body or f"{_PACKAGE_NAME}-{version}." in body


def probe_index(
    index_url: str,
    *,
    version: str | None = None,
    timeout: float = _PROBE_TIMEOUT_S,
) -> IndexProbe:
    """GET ``{index}/{package}/`` and classify reachability / version presence."""
    label = index_label(index_url)
    url = _index_package_url(index_url)
    started = time.monotonic()
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": f"{_PACKAGE_NAME}-updater/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        elapsed = time.monotonic() - started
        if page_has_package_version(body, version):
            return IndexProbe(index_url, label, elapsed, "has_version")
        detail = f"missing_version {version}" if version else "missing_version"
        return IndexProbe(index_url, label, elapsed, "missing_version", detail)
    except Exception as exc:
        elapsed = time.monotonic() - started
        exc_text = str(exc).lower()
        kind = (
            "timeout" if isinstance(exc, TimeoutError) or "timed out" in exc_text else "unreachable"
        )
        return IndexProbe(index_url, label, elapsed, "unreachable", f"{kind}: {exc}")


def rank_install_indexes(
    version: str | None,
    *,
    probe_timeout: float = _PROBE_TIMEOUT_S,
) -> tuple[list[tuple[str, str]], list[str]]:
    """Probe mirrors in parallel; return ``([(index_url, label), ...], skip_errors)``.

    Install candidates are indexes that list the target version, ordered by probe
    latency. ``pypi.org`` is always appended as a final fallback even when its
    probe fails (HTML parse misses / transient errors).
    """
    indexes = [*_MIRRORS, _PYPI_SIMPLE]
    probes: list[IndexProbe] = []
    with ThreadPoolExecutor(max_workers=len(indexes)) as pool:
        futures = [
            pool.submit(probe_index, url, version=version, timeout=probe_timeout) for url in indexes
        ]
        for fut in as_completed(futures):
            probes.append(fut.result())

    skip_errors: list[str] = []
    mirror_hits: list[IndexProbe] = []
    pypi_probe: IndexProbe | None = None
    for probe in probes:
        if probe.label == "pypi.org":
            pypi_probe = probe
            continue
        if probe.status == "has_version":
            mirror_hits.append(probe)
        else:
            skip_errors.append(f"{probe.label}: {probe.detail or probe.status}")

    mirror_hits.sort(key=lambda item: item.elapsed)
    ordered: list[tuple[str, str]] = [(item.index_url, item.label) for item in mirror_hits]

    if pypi_probe is not None and pypi_probe.status != "has_version":
        skip_errors.append(f"pypi.org: {pypi_probe.detail or pypi_probe.status}")
    ordered.append((_PYPI_SIMPLE, "pypi.org"))
    return ordered, skip_errors


def _all_mirrors_failed(mirror_errors: list[str]) -> UpgradeResult:
    hint = ""
    if mirror_errors:
        preferred = next(
            (
                err
                for err in mirror_errors
                if "missing_version" not in err and "unreachable:" not in err
            ),
            next(
                (err for err in mirror_errors if "missing_version" not in err),
                mirror_errors[0],
            ),
        )
        short = preferred if len(preferred) <= 120 else preferred[:117] + "..."
        hint = f" ({short})"
    return UpgradeResult(
        success=False,
        error=f"upgrade failed on all mirrors{hint}",
        mirror_errors=mirror_errors,
    )


def _run_install_cmd(
    cmd: list[str],
    label: str,
    *,
    verbose: bool,
    timeout: float,
) -> tuple[int | None, str]:
    logger.debug("running %s: %s", label, " ".join(cmd))
    try:
        # NOCA:DangerousSubprocessUseAudit(argv list with shell=False; installer paths and mirrors are trusted)
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=not verbose,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None, f"timed out after {int(timeout)}s"
    if result.returncode == 0:
        return 0, ""
    snippet = (result.stderr or result.stdout or "")[:300]
    return result.returncode, snippet


def _verify_fpk_upgrade(
    local_ver: str,
    site_packages: str,
    python_exe: str,
    mirror_errors: list[str],
    *,
    version: str | None = None,
    locale: str = DEFAULT_LOCALE,
) -> UpgradeResult:
    result = _verify_upgrade(
        local_ver,
        python_exe,
        mirror_errors,
        version=version,
        locale=locale,
        target=Path(site_packages),
    )
    if result.success:
        result.message = tr("update.fpk_completed", locale, version=result.installed_version)
    return result


def _run_fpk_upgrade(
    site_packages: str,
    *,
    verbose: bool = False,
    allow_prerelease: bool = False,
    version: str | None = None,
    locale: str = DEFAULT_LOCALE,
) -> UpgradeResult:
    """FnOS FPK 部署下的在线升级：把新版安装到 launcher 实际加载的打包目录。

    launcher 通过 PYTHONPATH 从应用中心托管的打包 site-packages 加载 octop，
    在线安装到系统 Python 永远不会被加载（重启后仍是旧版）。本函数把新版
    安装到该打包目录本身，重启服务后即加载新版，升级真正生效。

    与普通部署不同，FPK 首次在线升级需要从零解析并下载完整依赖树
    （octop 依赖 octop-harness 等大包），故安装超时显著放宽；先并行探测
    simple index，缺版本/不可达的镜像直接跳过，最后以 pypi.org 兜底。
    """
    if not os.path.isdir(site_packages):
        return UpgradeResult(
            success=False,
            error=tr("update.fpk_target_missing", locale, path=site_packages),
        )
    local_ver = get_local_version()
    ordered, mirror_errors = rank_install_indexes(version)
    python_exe = sys.executable
    installer = detect_installer()  # uv 优先：pip 对 octop-harness[all] 依赖树解析会卡死

    def _build_cmd(index_url: str) -> list[str]:
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
                "--index-url",
                index_url,
            ]
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
            "-i",
            index_url,
        ]
        append_prerelease_flags(cmd, installer, allow_prerelease=allow_prerelease)
        cmd.append(requirement)
        return cmd

    for index_url, label in ordered:
        rc, err_snippet = _run_install_cmd(
            _build_cmd(index_url),
            label,
            verbose=verbose,
            timeout=_TARGET_INSTALL_TIMEOUT_S,
        )
        if rc != 0:
            mirror_errors.append(f"{label}: {err_snippet or 'unknown error'}")
            continue
        res = _verify_fpk_upgrade(
            local_ver, site_packages, python_exe, mirror_errors, version=version, locale=locale
        )
        if res.success:
            return res
        # 镜像装到了同版本/旧版（同步滞后）：继续尝试下一个镜像
        mirror_errors.append(f"{label}: {res.error or 'version unchanged'}")

    return _all_mirrors_failed(mirror_errors)


def run_upgrade(
    *,
    verbose: bool = False,
    allow_prerelease: bool = False,
    version: str | None = None,
    locale: str = DEFAULT_LOCALE,
) -> UpgradeResult:
    try:
        validate_upgrade_target(version, get_local_version())
    except OctopError as exc:
        return UpgradeResult(success=False, error=exc.localized_message(locale))
    # Cache this running updater's locale bundles before installation replaces
    # its package resources, so result messages use the matching translations.
    lookup("update.completed", locale)
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
            locale=locale,
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
            locale=locale,
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
    locale: str = DEFAULT_LOCALE,
) -> UpgradeResult:
    installer = detect_installer()
    venv_python = resolve_venv_python()
    local_ver = get_local_version()
    target = green_packages_dir()
    ordered, mirror_errors = rank_install_indexes(version)
    fallback_deadline: float | None = None

    for index_url, label in ordered:
        if fallback_deadline is not None and time.monotonic() >= fallback_deadline:
            break
        cmd = build_upgrade_command(
            installer,
            venv_python,
            index_url=index_url,
            allow_prerelease=allow_prerelease,
            version=version,
        )
        if cmd is None:
            return UpgradeResult(
                success=False,
                error="pip is not available for the Octop virtual environment.",
                mirror_errors=mirror_errors,
            )
        fast_path = installer == "pip" and target is not None
        if fast_path and target is not None:
            pip_cmd = cmd[: cmd.index("install")]
            with tempfile.TemporaryDirectory(prefix="octop-upgrade-") as download_dir:
                download_timeout = float(_INSTALL_TIMEOUT_S)
                if fallback_deadline is not None:
                    download_timeout = min(download_timeout, fallback_deadline - time.monotonic())
                if download_timeout <= 0:
                    break
                download_cmd = [
                    *pip_cmd,
                    "download",
                    "--no-deps",
                    "--only-binary=:all:",
                    "--dest",
                    download_dir,
                    "-i",
                    index_url,
                ]
                append_prerelease_flags(download_cmd, installer, allow_prerelease=allow_prerelease)
                download_cmd.append(package_requirement(version))
                rc, err_snippet = _run_install_cmd(
                    download_cmd, label, verbose=verbose, timeout=download_timeout
                )
                if rc != 0:
                    # The fast path requires a prebuilt wheel. A download failure leaves
                    # the target untouched; try another mirror instead of a cold install.
                    mirror_errors.append(f"{label}: {err_snippet or 'unknown error'}")
                    continue
                wheels = list(Path(download_dir).glob("*.whl"))
                if len(wheels) == 1 and _target_dependencies_satisfied(
                    target, wheels[0], version=version
                ):
                    install_timeout = float(_INSTALL_TIMEOUT_S)
                    if fallback_deadline is not None:
                        install_timeout = min(install_timeout, fallback_deadline - time.monotonic())
                    if install_timeout <= 0:
                        break
                    rc, err_snippet = _run_install_cmd(
                        [
                            *pip_cmd,
                            "install",
                            "--no-index",
                            "--no-deps",
                            "--upgrade",
                            "--target",
                            str(target),
                            str(wheels[0]),
                        ],
                        label,
                        verbose=verbose,
                        timeout=install_timeout,
                    )
                    if rc == 0:
                        result = _verify_upgrade(
                            local_ver, venv_python, mirror_errors, version=version, locale=locale
                        )
                        if result.success:
                            return result
                logger.debug(
                    "%s: application-only upgrade unavailable; installing dependencies", label
                )

        timeout = float(_INSTALL_TIMEOUT_S)
        if fast_path:
            now = time.monotonic()
            if fallback_deadline is None:
                # One window starts at the first cold install, never once per mirror.
                # Use the constant itself: ``(now + budget) - now`` is not always
                # exactly ``budget`` for large monotonic clock values.
                fallback_deadline = now + _TARGET_INSTALL_TIMEOUT_S
                timeout = float(_TARGET_INSTALL_TIMEOUT_S)
            else:
                timeout = fallback_deadline - now
            if timeout <= 0:
                break
        rc, err_snippet = _run_install_cmd(cmd, label, verbose=verbose, timeout=timeout)
        if rc == 0:
            result = _verify_upgrade(
                local_ver, venv_python, mirror_errors, version=version, locale=locale
            )
            if result.success:
                return result
            err_snippet = result.error or tr("update.version_unavailable", locale)
        mirror_errors.append(f"{label}: {err_snippet or 'unknown error'}")

    return _all_mirrors_failed(mirror_errors)


def _verify_upgrade(
    local_ver: str,
    venv_python: str,
    mirror_errors: list[str],
    *,
    version: str | None = None,
    locale: str = DEFAULT_LOCALE,
    target: Path | None = None,
) -> UpgradeResult:
    target = target if target is not None else green_packages_dir()
    actual_ver: str | None = None
    for attempt in range(3):
        actual_ver = (
            get_version_in_dir(venv_python, str(target), check_cli=True)
            if target is not None
            else get_installed_version(venv_python)
        )
        if (
            actual_ver
            and is_newer(actual_ver, local_ver)
            and (version is None or parse_version(actual_ver) == parse_version(version))
        ):
            return UpgradeResult(
                success=True,
                message=tr("update.completed", locale, version=actual_ver),
                installed_version=actual_ver,
                mirror_errors=mirror_errors,
            )
        if attempt < 2:
            time.sleep(0.5)

    if actual_ver is None:
        error = tr("update.version_unavailable", locale)
    elif version is not None and parse_version(actual_ver) != parse_version(version):
        error = tr("update.version_mismatch", locale, actual=actual_ver, expected=version)
    else:
        error = tr("update.version_not_newer", locale, actual=actual_ver, previous=local_ver)
    return UpgradeResult(
        success=False,
        error=error,
        installed_version=actual_ver,
        mirror_errors=mirror_errors,
    )
