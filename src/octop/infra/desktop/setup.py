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


def install_script_rel() -> str:
    return "scripts/desktop/linux/v1.0/install.sh"


def start_script_rel() -> str:
    return "scripts/desktop/linux/v1.0/start.sh"


def _repo_candidates() -> list[Path]:
    out: list[Path] = []
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            out.append(parent)
            break
    cwd = Path.cwd()
    if (cwd / "pyproject.toml").is_file():
        out.append(cwd)
    return out


def resolve_install_script_path() -> Path | None:
    override = os.environ.get("OCTOP_DESKTOP_INSTALL_SCRIPT", "").strip()
    if override:
        path = Path(override)
        return path if path.is_file() else None
    for root in _repo_candidates():
        path = root / install_script_rel()
        if path.is_file():
            return path
    return None


def resolve_start_script_path() -> Path | None:
    override = os.environ.get("OCTOP_DESKTOP_START_SCRIPT", "").strip()
    if override:
        path = Path(override)
        return path if path.is_file() else None
    for root in _repo_candidates():
        path = root / start_script_rel()
        if path.is_file():
            return path
    return None


def resolve_resize_script_path() -> Path | None:
    override = os.environ.get("OCTOP_DESKTOP_RESIZE_SCRIPT", "").strip()
    if override:
        path = Path(override)
        return path if path.is_file() else None
    install = resolve_install_script_path()
    if install is not None:
        path = install.parent / "resize.sh"
        if path.is_file():
            return path
    for root in _repo_candidates():
        path = root / "scripts/desktop/linux/v1.0/resize.sh"
        if path.is_file():
            return path
    return None


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
        if os.geteuid() == 0:
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
        if os.geteuid() == 0
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

_DEPS_REASON = "Install Python extras: pip install 'octop[desktop]'"


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


def _virtual_desktop_installed() -> bool:
    return system_conf_dir().is_dir() or desktop_env_file().is_file()


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


def _check_vnc_localhost() -> tuple[bool | None, str]:
    bound = vnc_listens_localhost_only()
    if bound is False:
        return (
            False,
            "VNC port is exposed on the network; restart with -localhost yes (only 127.0.0.1)",
        )
    return bound, ""


def _display_usable(display: str) -> bool:
    if _xdpyinfo_ok(display):
        return True
    # xdpyinfo fails when TigerVNC hits MaxClients, but capture may still work.
    return _display_socket_ok(display) and _xvnc_process_ok(display)


def _resolve_linux_setup() -> tuple[SetupState, str | None, str, bool | None]:
    vnc_local, vnc_reason = _check_vnc_localhost()
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
            "Virtual desktop installed but not running; start octop-desktop services",
            vnc_local,
        )

    return (
        "needs_install",
        None,
        "No graphical display; install the Linux virtual desktop stack",
        vnc_local,
    )


def _mac_permissions() -> tuple[str, ...]:
    if platform.system() != "Darwin":
        return ()
    return ("screen_recording", "accessibility")


def desktop_status() -> DesktopStatus:
    system = platform.system().lower()
    install_script = install_script_rel()
    start_cmd = (
        "sudo systemctl start octop-desktop-xvnc octop-desktop-openbox octop-desktop-session"
    )
    geometry = read_geometry()

    if not _python_deps_available():
        return DesktopStatus(
            ok=False,
            desktop_supported=False,
            setup_state="deps_missing",
            platform=system,
            display=None,
            reason=_DEPS_REASON,
            install_script=install_script,
            start_command=start_cmd,
            geometry=geometry,
        )

    if system == "linux":
        setup_state, display, reason, vnc_local = _resolve_linux_setup()
        supported = setup_state in {"ready", "needs_start"}
        return DesktopStatus(
            ok=setup_state == "ready",
            desktop_supported=supported or setup_state == "needs_install",
            setup_state=setup_state,
            platform=system,
            display=display,
            reason=reason,
            install_script=install_script,
            start_command=start_cmd,
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
            install_script=install_script,
            start_command="",
            permissions_needed=(),
        )

    if system == "darwin":
        perms = _mac_permissions()
        return DesktopStatus(
            ok=True,
            desktop_supported=True,
            setup_state="ready",
            platform=system,
            display=None,
            reason="",
            install_script=install_script,
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
        install_script=install_script,
        start_command=start_cmd,
    )


def desktop_supported() -> tuple[bool, str]:
    status = desktop_status()
    if status.setup_state == "ready":
        return True, ""
    return False, status.reason or status.setup_state


def _sse(event: dict[str, object]) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def _stream_subprocess(cmd: list[str], *, cwd: Path | None = None) -> AsyncIterator[str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(cwd) if cwd else None,
    )
    assert proc.stdout is not None
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="replace").rstrip()
        if text:
            yield _sse({"log": text})
    code = await proc.wait()
    yield _sse({"done": True, "success": code == 0, "exit_code": code})


async def install_python_deps_stream() -> AsyncIterator[str]:
    yield _sse({"log": "Installing Python packages: mss, pynput, pillow..."})
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "mss>=9.0",
        "pynput>=1.7",
        "pillow>=10.0",
    ]
    async for chunk in _stream_subprocess(cmd):
        yield chunk


def _install_cmd_for_script(script: Path) -> list[str] | None:
    if os.geteuid() == 0:
        return ["/bin/bash", str(script)]
    if shutil.which("sudo"):
        return ["sudo", "-n", "/bin/bash", str(script)]
    return None


async def install_system_desktop_stream() -> AsyncIterator[str]:
    script = resolve_install_script_path()
    if script is None:
        yield _sse(
            {
                "done": True,
                "success": False,
                "error": "install script not found; run scripts/desktop/linux/v1.0/install.sh manually",
            }
        )
        return

    cmd = _install_cmd_for_script(script)
    if cmd is None:
        yield _sse(
            {
                "done": True,
                "success": False,
                "error": f"root or passwordless sudo required: sudo bash {script}",
            }
        )
        return

    yield _sse({"log": f"Running {script} ..."})
    async for chunk in _stream_subprocess(cmd, cwd=script.parent):
        yield chunk


async def start_desktop_stream() -> AsyncIterator[str]:
    script = resolve_start_script_path()
    if script is None:
        yield _sse(
            {
                "done": True,
                "success": False,
                "error": "start script not found",
            }
        )
        return

    cmd = _install_cmd_for_script(script)
    if cmd is None:
        yield _sse(
            {
                "done": True,
                "success": False,
                "error": f"root or passwordless sudo required: sudo bash {script}",
            }
        )
        return

    yield _sse({"log": f"Starting desktop services via {script} ..."})
    async for chunk in _stream_subprocess(cmd, cwd=script.parent):
        yield chunk


async def install_desktop_stream() -> AsyncIterator[str]:
    status = desktop_status()

    if status.setup_state == "deps_missing":
        async for chunk in install_python_deps_stream():
            yield chunk
            if chunk.startswith("data: "):
                payload = json.loads(chunk[6:].strip())
                if payload.get("done"):
                    if not payload.get("success"):
                        return
                    break
        status = desktop_status()

    if status.platform != "linux":
        yield _sse({"log": "Host desktop is ready on this platform."})
        yield _sse({"done": True, "success": status.setup_state == "ready"})
        return

    if status.setup_state == "needs_install":
        async for chunk in install_system_desktop_stream():
            yield chunk
        return

    if status.setup_state == "needs_start":
        async for chunk in start_desktop_stream():
            yield chunk
        return

    yield _sse({"log": "Desktop environment is already ready."})
    yield _sse({"done": True, "success": status.setup_state == "ready"})
