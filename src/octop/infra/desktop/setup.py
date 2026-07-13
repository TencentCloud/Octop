"""Remote desktop environment setup, probes, paths, and installation."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from octop.i18n import tr
from octop.infra.utils.posix_compat import geteuid

_SUBPROCESS_READ_CHUNK = 4096
_SUBPROCESS_MAX_LINE = 512 * 1024
_APT_LOCK_RE = re.compile(r"lock-frontend|dpkg.*lock", re.I)
_SCRIPT_LOG_RE = re.compile(
    r"(install\.sh|start\.sh|stop\.sh|Running /|Starting desktop services via /|Stopping desktop services via /)",
)


def _install_log(locale: str, key: str, **kwargs: object) -> str:
    text = tr(f"desktop.{key}", locale)
    return text.format(**kwargs) if kwargs else text


def _allowed_script_path(path: Path) -> bool:
    try:
        return bundled_scripts_dir().resolve() in path.resolve().parents
    except OSError:
        return False


def _script_path_from_env(env_var: str) -> Path | None:
    override = os.environ.get(env_var, "").strip()
    if not override:
        return None
    path = Path(override)
    if not path.is_file() or not _allowed_script_path(path):
        return None
    return path


def _bundled_script(name: str) -> Path | None:
    path = bundled_scripts_dir() / name
    return path if path.is_file() else None


def _sanitize_subprocess_log(text: str) -> str | None:
    t = text.strip()
    if not t or _SCRIPT_LOG_RE.search(t):
        return None
    return t


def _friendly_install_log_line(text: str, locale: str) -> str | None:
    t = text.strip()
    if not t:
        return None
    if _APT_LOCK_RE.search(t):
        return _install_log(locale, "error_apt_locked")
    if t.startswith("{") and t.endswith("}"):
        try:
            payload = json.loads(t)
        except json.JSONDecodeError:
            return t
        err = str(payload.get("error") or "").strip()
        if payload.get("installed") is False and err:
            if "apt" in err.lower():
                return _install_log(locale, "error_apt_failed")
            return err
    return t


async def _iter_subprocess_lines(stream: asyncio.StreamReader) -> AsyncIterator[str]:
    """Read subprocess stdout in chunks (apt/debconf may emit very long lines)."""
    buffer = b""
    while True:
        chunk = await stream.read(_SUBPROCESS_READ_CHUNK)
        if not chunk:
            if buffer:
                text = buffer.decode("utf-8", errors="replace").rstrip()
                if text:
                    yield text
            return
        buffer += chunk
        while b"\n" in buffer:
            raw, buffer = buffer.split(b"\n", 1)
            text = raw.decode("utf-8", errors="replace").rstrip()
            if text:
                yield text
        if len(buffer) > _SUBPROCESS_MAX_LINE:
            text = buffer.decode("utf-8", errors="replace").rstrip()
            if text:
                yield text
            buffer = b""


def octop_home() -> Path:
    return Path(os.environ.get("OCTOP_HOME", Path.home() / ".octop"))


def desktop_state_dir() -> Path:
    return octop_home() / "desktop"


def desktop_env_file() -> Path:
    return desktop_state_dir() / "desktop.env"


def system_conf_dir() -> Path:
    return Path("/etc/octop-desktop")


def system_install_root() -> Path:
    return Path("/opt/octop-desktop")


def bundled_scripts_dir() -> Path:
    return Path(__file__).resolve().parent / "scripts" / "linux" / "v1.0"


def resolve_install_script_path() -> Path | None:
    return _script_path_from_env("OCTOP_DESKTOP_INSTALL_SCRIPT") or _bundled_script("install.sh")


def resolve_start_script_path() -> Path | None:
    return _script_path_from_env("OCTOP_DESKTOP_START_SCRIPT") or _bundled_script("start.sh")


def resolve_stop_script_path() -> Path | None:
    return _script_path_from_env("OCTOP_DESKTOP_STOP_SCRIPT") or _bundled_script("stop.sh")


def resolve_resize_script_path() -> Path | None:
    return _script_path_from_env("OCTOP_DESKTOP_RESIZE_SCRIPT") or _bundled_script("resize.sh")


_DEFAULT_VNC_PORT = 5900
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "[::1]"})


def vnc_listens_localhost_only(port: int = _DEFAULT_VNC_PORT) -> bool | None:
    """Return True when VNC listens only on loopback, False if exposed, None if unknown."""
    listeners = _listeners_on_port(port)
    if listeners is None:
        return None
    if not listeners:
        return None
    return all(host in _LOOPBACK_HOSTS for host in listeners)


def _listeners_on_port(port: int) -> list[str] | None:
    if shutil.which("ss"):
        try:
            proc = subprocess.run(
                ["ss", "-ltn", f"sport = :{port}"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0:
            return None
        hosts: list[str] = []
        for line in proc.stdout.splitlines():
            match = re.search(rf"LISTEN\s+\d+\s+\d+\s+(\S+):{port}\b", line)
            if match:
                hosts.append(match.group(1))
        return hosts

    if shutil.which("netstat"):
        try:
            proc = subprocess.run(
                ["netstat", "-ltn"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0:
            return None
        hosts = []
        suffix = f":{port}"
        for line in proc.stdout.splitlines():
            if suffix not in line or "LISTEN" not in line:
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            addr = parts[3]
            if addr.endswith(suffix):
                hosts.append(addr[: -len(suffix)])
        return hosts

    return None


_GEOMETRY_RE = re.compile(r"^(\d{3,5})x(\d{3,5})$")
_DEFAULT_GEOMETRY = "1920x1080"


def parse_geometry(value: str) -> tuple[int, int]:
    match = _GEOMETRY_RE.match(value.strip())
    if not match:
        raise ValueError(f"invalid geometry: {value!r}")
    width, height = int(match.group(1)), int(match.group(2))
    if width < 640 or height < 480 or width > 7680 or height > 4320:
        raise ValueError(f"geometry out of range: {value}")
    return width, height


def read_geometry() -> str:
    path = desktop_env_file()
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("export OCTOP_DESKTOP_GEOMETRY="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if _GEOMETRY_RE.match(value):
                    return value
            if line.startswith("OCTOP_DESKTOP_GEOMETRY="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if _GEOMETRY_RE.match(value):
                    return value
    return os.environ.get("OCTOP_DESKTOP_GEOMETRY", _DEFAULT_GEOMETRY)


def _write_geometry_env(geometry: str) -> None:
    path = desktop_env_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    display = ":99"
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("export DISPLAY=") or line.startswith("DISPLAY="):
                display = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    path.write_text(
        "\n".join(
            [
                f"export DISPLAY={display}",
                f"export OCTOP_DESKTOP_DISPLAY={display}",
                f"export OCTOP_DESKTOP_GEOMETRY={geometry}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def apply_geometry(geometry: str) -> None:
    parse_geometry(geometry)

    resize_script = resolve_resize_script_path()
    if resize_script is not None:
        cmd: list[str]
        if geteuid() == 0:
            cmd = ["/bin/bash", str(resize_script), geometry]
        elif shutil.which("sudo"):
            cmd = ["sudo", "-n", "/bin/bash", str(resize_script), geometry]
        else:
            raise PermissionError("root or passwordless sudo required to change desktop geometry")
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
        if proc.returncode != 0:
            detail = (proc.stdout or proc.stderr or "").strip()
            raise RuntimeError(detail or f"resize failed with exit {proc.returncode}")
        _write_geometry_env(geometry)
        return

    start_script = resolve_start_script_path()
    if start_script is None:
        raise RuntimeError("desktop resize script not found")
    cmd = (
        ["/bin/bash", str(start_script)]
        if geteuid() == 0
        else ["sudo", "-n", "/bin/bash", str(start_script)]
    )
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    if proc.returncode != 0:
        detail = (proc.stdout or proc.stderr or "").strip()
        raise RuntimeError(detail or "failed to restart desktop after geometry change")
    _write_geometry_env(geometry)


SetupState = Literal[
    "ready",
    "needs_install",
    "needs_start",
    "unsupported",
    "deps_missing",
    "permission_denied",
]


def python_deps_install_cmd() -> list[str] | None:
    """Build install command for desktop optional Python packages."""
    packages = ["mss>=9.0", "pynput>=1.7", "pillow>=10.0"]
    uv_bin = shutil.which("uv")
    if uv_bin:
        return [uv_bin, "pip", "install", "--python", sys.executable, *packages]
    if importlib.util.find_spec("pip") is not None:
        return [sys.executable, "-m", "pip", "install", *packages]
    return None


def python_deps_uninstall_cmd() -> list[str] | None:
    """Build uninstall command for desktop optional Python packages."""
    packages = ["mss", "pynput", "pillow"]
    uv_bin = shutil.which("uv")
    if uv_bin:
        return [uv_bin, "pip", "uninstall", "-y", *packages, "--python", sys.executable]
    if importlib.util.find_spec("pip") is not None:
        return [sys.executable, "-m", "pip", "uninstall", "-y", *packages]
    return None


@dataclass(frozen=True)
class DesktopStatus:
    ok: bool
    desktop_supported: bool
    setup_state: SetupState
    platform: str
    display: str | None
    reason: str
    install_script: str
    start_command: str
    geometry: str = "1920x1080"
    permissions_needed: tuple[str, ...] = ()
    vnc_localhost_only: bool | None = None


def _python_deps_available() -> bool:
    return (
        importlib.util.find_spec("mss") is not None
        and importlib.util.find_spec("pynput") is not None
        and importlib.util.find_spec("PIL") is not None
    )


def _display_from_env_file() -> str | None:
    path = desktop_env_file()
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("export DISPLAY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
        if line.startswith("DISPLAY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _display_socket_ok(display: str) -> bool:
    num = display.lstrip(":")
    if num.isdigit():
        sock = Path(f"/tmp/.X11-unix/X{num}")
        if sock.exists():
            return True
    return False


def _xvnc_process_ok(display: str) -> bool:
    num = display.lstrip(":")
    try:
        proc = subprocess.run(
            ["pgrep", "-f", f":{num}"],
            capture_output=True,
            timeout=3,
            check=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _xdpyinfo_ok(display: str) -> bool:
    if not shutil.which("xdpyinfo"):
        return _display_socket_ok(display) and _xvnc_process_ok(display)
    env = os.environ.copy()
    env["DISPLAY"] = display
    try:
        proc = subprocess.run(
            ["xdpyinfo", "-display", display],
            env=env,
            capture_output=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def _systemd_available() -> bool:
    return shutil.which("systemctl") is not None and Path("/run/systemd/system").is_dir()


def _systemd_unit_files() -> tuple[Path, ...]:
    return (
        Path("/etc/systemd/system/octop-desktop-xvnc.service"),
        Path("/etc/systemd/system/octop-desktop-session.service"),
        Path("/etc/systemd/system/octop-desktop-openbox.service"),
    )


def _systemd_unit_files_present() -> bool:
    return all(path.is_file() for path in _systemd_unit_files())


def _runtime_scripts_present() -> bool:
    root = system_install_root()
    return (root / "start-openbox.sh").is_file() and (root / "start-session.sh").is_file()


def _virtual_desktop_installed() -> bool:
    """True when the stack is complete enough to start (not a partial leftover)."""
    if not _runtime_scripts_present():
        return False
    if not (system_conf_dir().is_dir() or desktop_env_file().is_file()):
        return False
    if _systemd_available():
        return _systemd_unit_files_present()
    return True


def _linux_virtual_desktop_present() -> bool:
    """True when any virtual-desktop leftover exists (including partial installs)."""
    return (
        system_conf_dir().is_dir()
        or system_install_root().is_dir()
        or desktop_env_file().is_file()
        or _systemd_unit_files_present()
    )


def _desktop_uninstall_succeeded() -> bool:
    """True when optional Python deps and the Linux virtual stack are gone."""
    if not _python_deps_available():
        return True
    if platform.system().lower() == "linux":
        return not _linux_virtual_desktop_present()
    return False


def _xvnc_service_active() -> bool:
    if shutil.which("systemctl") and Path("/run/systemd/system").is_dir():
        try:
            proc = subprocess.run(
                ["systemctl", "is-active", "--quiet", "octop-desktop-xvnc"],
                capture_output=True,
                timeout=3,
                check=False,
            )
            if proc.returncode == 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            pass

    try:
        proc = subprocess.run(
            ["pgrep", "-f", r"X(vnc|tigervnc).*:99"],
            capture_output=True,
            timeout=3,
            check=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _check_vnc_localhost(*, locale: str = "en") -> tuple[bool | None, str]:
    bound = vnc_listens_localhost_only()
    if bound is False:
        return False, _install_log(locale, "error_vnc_exposed")
    return bound, ""


def _display_usable(display: str) -> bool:
    if _xdpyinfo_ok(display):
        return True
    # xdpyinfo fails when TigerVNC hits MaxClients, but capture may still work.
    return _display_socket_ok(display) and _xvnc_process_ok(display)


def _resolve_linux_setup(*, locale: str = "en") -> tuple[SetupState, str | None, str, bool | None]:
    vnc_local, vnc_reason = _check_vnc_localhost(locale=locale)
    display = os.environ.get("DISPLAY", "").strip() or _display_from_env_file()
    if display and _display_usable(display):
        if vnc_local is False:
            return "needs_start", display, vnc_reason, vnc_local
        return "ready", display, "", vnc_local

    if os.environ.get("WAYLAND_DISPLAY") and not display:
        return (
            "unsupported",
            None,
            "Wayland session without X11; run the Linux virtual desktop install script",
            vnc_local,
        )

    if _virtual_desktop_installed():
        if _xvnc_service_active():
            display = display or ":99"
            if _display_usable(display):
                if vnc_local is False:
                    return "needs_start", display, vnc_reason, vnc_local
                return "ready", display, "", vnc_local
        return (
            "needs_start",
            None,
            "",
            vnc_local,
        )

    return (
        "needs_install",
        None,
        "",
        vnc_local,
    )


def _mac_screen_recording_granted() -> bool | None:
    """Return True/False from TCC, or None if the probe API is unavailable."""
    try:
        from Quartz import CGPreflightScreenCaptureAccess
    except ImportError:
        return None
    try:
        return bool(CGPreflightScreenCaptureAccess())
    except Exception:
        return None


def _mac_accessibility_granted() -> bool | None:
    """Return True/False from TCC, or None if the probe API is unavailable."""
    try:
        from ApplicationServices import AXIsProcessTrusted
    except ImportError:
        try:
            from HIServices import AXIsProcessTrusted
        except ImportError:
            return None
    try:
        return bool(AXIsProcessTrusted())
    except Exception:
        return None


def _mac_permissions() -> tuple[str, ...]:
    """Only list macOS TCC grants that are actually missing (probe, do not prompt)."""
    if platform.system() != "Darwin":
        return ()
    missing: list[str] = []
    screen = _mac_screen_recording_granted()
    if screen is False:
        missing.append("screen_recording")
    access = _mac_accessibility_granted()
    if access is False:
        missing.append("accessibility")
    return tuple(missing)


def desktop_status(*, locale: str = "en") -> DesktopStatus:
    system = platform.system().lower()
    geometry = read_geometry()

    if not _python_deps_available():
        return DesktopStatus(
            ok=False,
            desktop_supported=system in {"linux", "darwin", "windows"},
            setup_state="deps_missing",
            platform=system,
            display=None,
            reason=_install_log(locale, "deps_reason"),
            install_script="",
            start_command="",
            geometry=geometry,
            # Defer TCC probes until desktop deps are present.
            permissions_needed=(),
        )

    if system == "linux":
        setup_state, display, reason, vnc_local = _resolve_linux_setup(locale=locale)
        supported = setup_state in {"ready", "needs_start"}
        return DesktopStatus(
            ok=setup_state == "ready",
            desktop_supported=supported or setup_state == "needs_install",
            setup_state=setup_state,
            platform=system,
            display=display,
            reason=reason,
            install_script="",
            start_command="",
            geometry=geometry,
            vnc_localhost_only=vnc_local,
        )

    if system == "windows":
        return DesktopStatus(
            ok=True,
            desktop_supported=True,
            setup_state="ready",
            platform=system,
            display=None,
            reason="",
            install_script="",
            start_command="",
            permissions_needed=(),
        )

    if system == "darwin":
        perms = _mac_permissions()
        return DesktopStatus(
            ok=not perms,
            desktop_supported=True,
            setup_state="ready",
            platform=system,
            display=None,
            reason="",
            install_script="",
            start_command="",
            permissions_needed=perms,
        )

    return DesktopStatus(
        ok=False,
        desktop_supported=False,
        setup_state="unsupported",
        platform=system,
        display=None,
        reason=f"Unsupported platform: {system}",
        install_script="",
        start_command="",
    )


def desktop_supported() -> tuple[bool, str]:
    status = desktop_status()
    if status.setup_state == "ready":
        return True, ""
    return False, status.reason or status.setup_state


def _sse(event: dict[str, object]) -> str:
    return f"data: {json.dumps(event)}\n\n"


@dataclass
class _SubprocessRun:
    exit_code: int | None = None


async def _stream_subprocess(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    emit_done: bool = True,
    result: _SubprocessRun | None = None,
    sanitize_paths: bool = False,
    locale: str = "en",
) -> AsyncIterator[str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(cwd) if cwd else None,
    )
    assert proc.stdout is not None
    stream_error = False
    try:
        async for line in _iter_subprocess_lines(proc.stdout):
            text = line
            if sanitize_paths:
                sanitized = _sanitize_subprocess_log(text)
                if sanitized is None:
                    continue
                text = sanitized
            friendly = _friendly_install_log_line(text, locale)
            if friendly is None:
                continue
            yield _sse({"log": friendly})
    except Exception:
        stream_error = True
        yield _sse({"log": _install_log(locale, "error_subprocess_stream")})
    code = await proc.wait()
    if stream_error and code == 0:
        code = 1
    if result is not None:
        result.exit_code = code
    if emit_done:
        yield _sse({"done": True, "success": code == 0, "exit_code": code})


async def _install_failure(message: str) -> AsyncIterator[str]:
    yield _sse({"done": True, "success": False, "error": message, "log": message})


async def _probe_desktop_status(*, locale: str = "en") -> DesktopStatus:
    return await asyncio.to_thread(desktop_status, locale=locale)


async def _run_script_step(
    script: Path | None,
    *,
    locale: str,
    missing_error_key: str,
    log_message_key: str,
    tolerate_exit_code: bool = False,
) -> AsyncIterator[str]:
    if script is None:
        async for chunk in _install_failure(_install_log(locale, missing_error_key)):
            yield chunk
        return
    cmd = _install_cmd_for_script(script)
    if cmd is None:
        async for chunk in _install_failure(_install_log(locale, "error_sudo_required")):
            yield chunk
        return
    yield _sse({"log": _install_log(locale, log_message_key)})
    run = _SubprocessRun()
    async for chunk in _stream_subprocess(
        cmd,
        cwd=script.parent,
        emit_done=False,
        result=run,
        sanitize_paths=True,
        locale=locale,
    ):
        yield chunk
    if run.exit_code != 0:
        if tolerate_exit_code:
            yield _sse({"log": _install_log(locale, "install_log_stop_skipped")})
            return
        async for chunk in _install_failure(
            _install_log(locale, "error_command_failed", exit_code=run.exit_code)
        ):
            yield chunk


async def install_python_deps_stream(locale: str) -> AsyncIterator[str]:
    cmd = python_deps_install_cmd()
    if cmd is None:
        async for chunk in _install_failure(_install_log(locale, "error_pip_unavailable")):
            yield chunk
        return
    yield _sse({"log": _install_log(locale, "install_log_deps")})
    run = _SubprocessRun()
    async for chunk in _stream_subprocess(cmd, emit_done=False, result=run, locale=locale):
        yield chunk
    if run.exit_code != 0:
        async for chunk in _install_failure(
            _install_log(locale, "error_pip_install_failed", exit_code=run.exit_code)
        ):
            yield chunk


def _install_cmd_for_script(script: Path) -> list[str] | None:
    if geteuid() == 0:
        return ["/bin/bash", str(script)]
    if shutil.which("sudo"):
        return ["sudo", "-n", "/bin/bash", str(script)]
    return None


def _sudo_shell_cmd(script: str) -> list[str] | None:
    if geteuid() == 0:
        return ["/bin/bash", "-c", script]
    if shutil.which("sudo"):
        return ["sudo", "-n", "/bin/bash", "-c", script]
    return None


_LINUX_UNINSTALL_SHELL = """
set -euo pipefail
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  systemctl disable octop-desktop-xvnc octop-desktop-openbox octop-desktop-session 2>/dev/null || true
  systemctl stop octop-desktop-xvnc octop-desktop-openbox octop-desktop-session 2>/dev/null || true
  systemctl reset-failed octop-desktop-xvnc octop-desktop-openbox octop-desktop-session 2>/dev/null || true
  systemctl daemon-reload 2>/dev/null || true
fi
rm -f /etc/systemd/system/octop-desktop-xvnc.service \\
      /etc/systemd/system/octop-desktop-openbox.service \\
      /etc/systemd/system/octop-desktop-session.service
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  systemctl daemon-reload 2>/dev/null || true
fi
rm -rf /opt/octop-desktop /etc/octop-desktop
rm -f /usr/share/backgrounds/octop-desktop-wallpaper.png \\
      /usr/share/backgrounds/octop-desktop-wallpaper.svg 2>/dev/null || true
rm -f /usr/share/icons/hicolor/48x48/apps/octop-start-menu.png 2>/dev/null || true
# Stale xfconf/icon layout survives a package reinstall and keeps tiny icons.
rm -rf /root/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-desktop.xml \\
       /root/.config/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml \\
       /root/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml \\
       /root/.config/xfce4/desktop \\
       /root/.config/xfce4/panel \\
       /root/.cache/xfce4/xfdesktop 2>/dev/null || true
pkill -9 -f 'import -display :99' 2>/dev/null || true
pkill -9 -f 'Xvnc :99' 2>/dev/null || true
pkill -9 -f '/opt/octop-desktop/' 2>/dev/null || true
pkill -x xfce4-panel 2>/dev/null || true
pkill -f 'xfdesktop --display' 2>/dev/null || true
rm -f /tmp/.X99-lock
rm -rf /tmp/.X11-unix/X99 /tmp/octop-desktop-dbus-env /tmp/runtime-octop-desktop
"""


def _remove_local_desktop_state() -> None:
    shutil.rmtree(desktop_state_dir(), ignore_errors=True)


async def install_system_desktop_stream(locale: str) -> AsyncIterator[str]:
    async for chunk in _run_script_step(
        resolve_install_script_path(),
        locale=locale,
        missing_error_key="error_script_missing",
        log_message_key="install_log_system",
    ):
        yield chunk


async def start_desktop_stream(locale: str) -> AsyncIterator[str]:
    async for chunk in _run_script_step(
        resolve_start_script_path(),
        locale=locale,
        missing_error_key="error_start_script_missing",
        log_message_key="install_log_start",
    ):
        yield chunk


def _sse_done(chunk: str) -> dict[str, object] | None:
    if not chunk.startswith("data: "):
        return None
    payload = json.loads(chunk[6:].strip())
    return payload if payload.get("done") else None


async def install_desktop_stream(*, locale: str = "en") -> AsyncIterator[str]:
    for _attempt in range(6):
        status = await _probe_desktop_status(locale=locale)

        if status.setup_state == "ready":
            yield _sse({"log": _install_log(locale, "install_log_ready")})
            yield _sse({"done": True, "success": True})
            return

        if status.setup_state == "deps_missing":
            async for chunk in install_python_deps_stream(locale):
                yield chunk
                done = _sse_done(chunk)
                if done is not None and not done.get("success"):
                    return
            await asyncio.sleep(0.3)
            continue

        if status.platform != "linux":
            yield _sse({"log": _install_log(locale, "install_log_host_ready")})
            yield _sse({"done": True, "success": status.ok})
            return

        if status.setup_state == "needs_install":
            async for chunk in install_system_desktop_stream(locale):
                yield chunk
                done = _sse_done(chunk)
                if done is not None and not done.get("success"):
                    return
            await asyncio.sleep(2)
            continue

        if status.setup_state == "needs_start":
            async for chunk in start_desktop_stream(locale):
                yield chunk
                done = _sse_done(chunk)
                if done is not None and not done.get("success"):
                    return
            await asyncio.sleep(1)
            continue

        async for chunk in _install_failure(status.reason or status.setup_state):
            yield chunk
        return

    for _ in range(15):
        status = await _probe_desktop_status(locale=locale)
        if status.setup_state == "ready":
            yield _sse({"log": _install_log(locale, "install_log_ready")})
            yield _sse({"done": True, "success": True})
            return
        await asyncio.sleep(1)

    status = await _probe_desktop_status(locale=locale)
    if status.setup_state == "ready":
        yield _sse({"log": _install_log(locale, "install_log_ready")})
        yield _sse({"done": True, "success": True})
        return
    async for chunk in _install_failure(_install_log(locale, "error_setup_timeout")):
        yield chunk


async def uninstall_python_deps_stream(locale: str) -> AsyncIterator[str]:
    if not _python_deps_available():
        return
    cmd = python_deps_uninstall_cmd()
    if cmd is None:
        yield _sse({"log": _install_log(locale, "error_pip_remove_skipped")})
        return
    yield _sse({"log": _install_log(locale, "install_log_remove_python")})
    run = _SubprocessRun()
    async for chunk in _stream_subprocess(cmd, emit_done=False, result=run, locale=locale):
        yield chunk
    if run.exit_code not in {0, None} and _python_deps_available():
        async for chunk in _install_failure(
            _install_log(locale, "error_pip_remove_failed", exit_code=run.exit_code)
        ):
            yield chunk


async def uninstall_linux_stack_stream(locale: str) -> AsyncIterator[str]:
    if not _linux_virtual_desktop_present():
        return

    stop = resolve_stop_script_path()
    if stop is not None:
        async for chunk in _run_script_step(
            stop,
            locale=locale,
            missing_error_key="error_stop_script_missing",
            log_message_key="install_log_stop_services",
            tolerate_exit_code=True,
        ):
            yield chunk
            done = _sse_done(chunk)
            if done is not None and not done.get("success"):
                return

    cmd = _sudo_shell_cmd(_LINUX_UNINSTALL_SHELL)
    if cmd is None:
        async for chunk in _install_failure(_install_log(locale, "error_sudo_uninstall_required")):
            yield chunk
        return

    yield _sse({"log": _install_log(locale, "install_log_remove_system")})
    run = _SubprocessRun()
    async for chunk in _stream_subprocess(
        cmd, emit_done=False, result=run, sanitize_paths=True, locale=locale
    ):
        yield chunk
    if run.exit_code != 0:
        async for chunk in _install_failure(
            _install_log(locale, "error_command_failed", exit_code=run.exit_code)
        ):
            yield chunk


async def uninstall_desktop_stream(*, locale: str = "en") -> AsyncIterator[str]:
    from octop.infra.desktop.session import disconnect_all_streams

    yield _sse({"log": _install_log(locale, "install_log_closing_streams")})
    await disconnect_all_streams()

    status = await _probe_desktop_status(locale=locale)
    if status.platform == "linux":
        async for chunk in uninstall_linux_stack_stream(locale):
            yield chunk
            done = _sse_done(chunk)
            if done is not None and not done.get("success"):
                return

    _remove_local_desktop_state()

    async for chunk in uninstall_python_deps_stream(locale):
        yield chunk
        done = _sse_done(chunk)
        if done is not None and not done.get("success"):
            return

    if _desktop_uninstall_succeeded():
        yield _sse({"log": _install_log(locale, "install_log_removed")})
        yield _sse({"done": True, "success": True})
        return
    async for chunk in _install_failure(_install_log(locale, "error_uninstall_incomplete")):
        yield chunk
