"""Automatic Docker install for the Android container backend.

Design notes:
- No geo detection: the install source is picked by a pure latency race that
  includes the official https://download.docker.com (fastest wins; when the
  official source wins, no ``DOWNLOAD_URL`` override is passed).
- Installs via the bundled official get.docker.com script (vendored copy at
  scripts/linux/v1.0/install-docker.sh) so hosts the online script does not
  support (TencentOS / OpenCloudOS releasever mapping, offline curl failures,
  etc.) still install, and we never pipe the network straight into ``sh``.
- Registry-mirror config probes Tencent Cloud's mirror reachability (again no
  geo check) and runs only right after a fresh install, so a daemon that may
  already be running user containers is never restarted.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shutil
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path

from octop.i18n import tr
from octop.infra.utils.posix_compat import geteuid

# Official source first; latency race decides (no region detection).
_DOCKER_CE_SOURCES = (
    "https://download.docker.com",
    "https://mirrors.aliyun.com/docker-ce",
    "https://mirrors.tencent.com/docker-ce",
    "https://mirrors.163.com/docker-ce",
    "https://mirrors.cernet.edu.cn/docker-ce",
)
_OFFICIAL_SOURCE = "https://download.docker.com"
_TENCENT_MIRROR_HOST = "mirror.ccs.tencentyun.com"
_TENCENT_MIRROR_URL = f"https://{_TENCENT_MIRROR_HOST}/"
_DAEMON_JSON = Path("/etc/docker/daemon.json")

_SPEED_TEST_ITERATIONS = 3
_SPEED_TEST_TIMEOUT = 5.0
_PROBE_TIMEOUT = 3.0
_DAEMON_READY_TIMEOUT = 10.0
_DAEMON_WAIT_AFTER_RESTART = 30.0
_DAEMON_WAIT_INTERVAL = 2.0
# The vendored script sleeps 20s when docker already exists, and package
# manager steps can take minutes on slow links; keep the read patient.
_SCRIPT_READLINE_TIMEOUT = 600.0
_SCRIPT_TAIL_LINES = 40

# Known fatal script outputs → friendly localized hints. Matched
# case-insensitively against the tail of the script output.
_SCRIPT_ERROR_HINTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"unsupported (?:operating system|distribution)", re.I),
        "docker_hint_unsupported_distro",
    ),
    (re.compile(r"needs the ability to run commands as root", re.I), "docker_hint_no_root"),
    (re.compile(r"unable to find either .sudo. or .su.", re.I), "docker_hint_no_root"),
    (re.compile(r"command appears to already exist", re.I), "docker_hint_already_installed"),
    (re.compile(r"curl", re.I), "docker_hint_network"),
    (
        re.compile(r"(?:apt|apt-get|dpkg|dnf|yum).*?(?:error|failed|lock)", re.I),
        "docker_hint_pkg_manager",
    ),
    (
        re.compile(r"^E: .*(?:lock|unable to locate|not available)", re.I | re.M),
        "docker_hint_pkg_manager",
    ),
    (re.compile(r"key.*(?:expired|not found|rejected)", re.I), "docker_hint_gpg_key"),
    (re.compile(r"no space left on device", re.I), "docker_hint_disk_full"),
)


def _log(locale: str, key: str, **kwargs: object) -> str:
    text = tr(f"mobile.{key}", locale)
    return text.format(**kwargs) if kwargs else text


def bundled_scripts_dir() -> Path:
    return Path(__file__).resolve().parent / "scripts" / "linux" / "v1.0"


def bundled_install_script() -> Path:
    """Path of the vendored official Docker install script."""
    return bundled_scripts_dir() / "install-docker.sh"


def _classify_script_error(lines: list[str]) -> str | None:
    """Map the tail of script output onto a friendly hint key, if any."""
    tail = "\n".join(lines[-_SCRIPT_TAIL_LINES:])
    for pattern, key in _SCRIPT_ERROR_HINTS:
        if pattern.search(tail):
            return key
    return None


async def _measure_source_delay(url: str) -> float | None:
    """Average curl time_total over a few probes; None when unreachable."""
    if shutil.which("curl") is None:
        return None
    times: list[float] = []
    for _ in range(_SPEED_TEST_ITERATIONS):
        try:
            proc = await asyncio.create_subprocess_exec(
                "curl",
                "-o",
                "/dev/null",
                "-s",
                "-w",
                "%{time_total}",
                "--connect-timeout",
                "3",
                "-m",
                str(_SPEED_TEST_TIMEOUT),
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError:
            return None
        out, _ = await proc.communicate()
        if proc.returncode != 0:
            return None
        try:
            times.append(float(out.decode("utf-8", errors="replace").strip()))
        except ValueError:
            return None
    return sum(times) / len(times)


async def select_download_source() -> tuple[str | None, float | None]:
    """Latency-race all sources.

    Returns ``(mirror_url, delay)`` for the fastest mirror, ``(None, delay)``
    when the official source wins (caller must not set ``DOWNLOAD_URL``), or
    ``(None, None)`` when nothing is reachable.
    """
    best_source: str | None = None
    best_delay: float | None = None
    for source in _DOCKER_CE_SOURCES:
        delay = await _measure_source_delay(source)
        if delay is None:
            continue
        if best_delay is None or delay < best_delay:
            best_delay = delay
            best_source = None if source == _OFFICIAL_SOURCE else source
    return best_source, best_delay


def can_install_without_password() -> bool:
    """Whether this process may install packages (root or passwordless sudo)."""
    if geteuid() == 0:
        return True
    if shutil.which("sudo") is None:
        return False
    try:
        proc = subprocess.run(
            ["sudo", "-n", "true"],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


async def docker_daemon_ready(timeout: float = _DAEMON_READY_TIMEOUT) -> bool:
    """Docker CLI present and the daemon answers."""
    if shutil.which("docker") is None:
        return False
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "version",
            "--format",
            "{{.Server.Version}}",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except (TimeoutError, OSError):
        return False
    return proc.returncode == 0


async def _probe_tencent_mirror() -> bool:
    """Plain TCP reachability check for the Tencent Cloud registry mirror."""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(_TENCENT_MIRROR_HOST, 443), timeout=_PROBE_TIMEOUT
        )
    except (TimeoutError, OSError):
        return False
    writer.close()
    with contextlib.suppress(OSError):
        await writer.wait_closed()
    return True


def _merge_registry_mirror(daemon_json: Path, mirror: str) -> bool:
    """Add ``registry-mirrors`` to daemon.json unless already configured.

    Backs up the previous file as ``daemon.json.backup``. Returns True when the
    file was written; False when left untouched (already configured, or the
    existing file is unreadable/corrupt).
    """
    config: dict[str, object] = {}
    if daemon_json.exists():
        try:
            loaded = json.loads(daemon_json.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if not isinstance(loaded, dict):
            return False
        config = loaded
    if "registry-mirrors" in config:
        return False
    if not daemon_json.parent.exists():
        return False
    if daemon_json.exists():
        try:
            shutil.copy2(daemon_json, daemon_json.parent / f"{daemon_json.name}.backup")
        except OSError:
            return False
    config["registry-mirrors"] = [mirror]
    try:
        daemon_json.write_text(
            json.dumps(config, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return False
    return True


async def _restart_docker_daemon() -> bool:
    for cmd in (
        ("systemctl", "restart", "docker"),
        ("service", "docker", "restart"),
    ):
        if shutil.which(cmd[0]) is None:
            continue
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.communicate(), timeout=_DAEMON_READY_TIMEOUT)
        except (TimeoutError, OSError):
            continue
        if proc.returncode == 0:
            return True
    return False


async def _wait_for_daemon(seconds: float) -> bool:
    deadline = asyncio.get_running_loop().time() + seconds
    while True:
        if await docker_daemon_ready():
            return True
        if asyncio.get_running_loop().time() >= deadline:
            return False
        await asyncio.sleep(_DAEMON_WAIT_INTERVAL)


async def auto_install_docker_stream(*, locale: str = "en") -> AsyncIterator[str]:
    """Yield human-readable log lines for the automatic Docker install.

    Success is judged by the caller via :func:`docker_daemon_ready`, so this
    generator only reports what happened.
    """
    # 0) The vendored official script must ship with this Octop install.
    script = bundled_install_script()
    if not script.is_file():
        yield _log(locale, "docker_install_script_missing")
        return

    # 1) Latency-race install sources (official included, no geo detection).
    source, delay = await select_download_source()
    if delay is not None and source is None:
        yield _log(locale, "docker_source_official")
    elif source is not None and delay is not None:
        yield _log(locale, "docker_source_selected", source=source, delay=round(delay, 3))
    else:
        yield _log(locale, "docker_source_fallback")

    # 2) Run the bundled official install script; a winning mirror rides on
    #    DOWNLOAD_URL (the script honours a preset DOWNLOAD_URL env var).
    env = {k: v for k, v in os.environ.items() if k != "DOWNLOAD_URL"}
    if source is not None:
        env["DOWNLOAD_URL"] = source
    yield _log(locale, "docker_install_log_start")
    output_lines: list[str] = []
    try:
        proc = await asyncio.create_subprocess_exec(
            "sh",
            str(script),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
    except OSError as exc:
        yield _log(locale, "docker_install_spawn_failed", error=str(exc))
        return
    assert proc.stdout is not None
    while True:
        try:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=_SCRIPT_READLINE_TIMEOUT)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            yield _log(locale, "docker_install_stalled")
            return
        if not line:
            break
        text = line.decode("utf-8", errors="replace").strip()
        if text:
            output_lines.append(text)
            yield text
    code = await proc.wait()
    if code != 0:
        yield _log(locale, "docker_install_script_failed", exit_code=code)
        hint_key = _classify_script_error(output_lines)
        if hint_key is not None:
            yield _log(locale, hint_key)
        return

    # 3) Registry mirror: only probe reachability, only for this fresh install.
    if await _probe_tencent_mirror():
        yield _log(locale, "docker_mirror_reachable")
        if _merge_registry_mirror(_DAEMON_JSON, _TENCENT_MIRROR_URL):
            yield _log(locale, "docker_mirror_configured")
            if await _restart_docker_daemon():
                yield _log(locale, "docker_restart_ok")
                if await _wait_for_daemon(_DAEMON_WAIT_AFTER_RESTART):
                    yield _log(locale, "docker_restart_ready")
                else:
                    yield _log(locale, "docker_restart_failed")
            else:
                yield _log(locale, "docker_restart_failed")
        else:
            yield _log(locale, "docker_mirror_skipped")
    else:
        yield _log(locale, "docker_mirror_unreachable")
