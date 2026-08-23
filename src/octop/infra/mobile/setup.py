"""Runtime mobile status and optional container install."""

from __future__ import annotations

import asyncio
import json
import platform
import shutil
import subprocess
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from octop.config import OctopConfig
from octop.i18n import tr
from octop.infra.mobile.adb import adb_connect, find_adb, list_devices

SetupState = Literal["needs_device", "needs_install", "ready", "unsupported"]
MobileBackend = Literal["physical", "redroid", "emulator", "none"]

_CONTAINER_NAME = "octop-mobile-android"
_CONTAINER_ADB_ENDPOINT = "127.0.0.1:5555"


def _mobile_log(locale: str, key: str, **kwargs: object) -> str:
    text = tr(f"mobile.{key}", locale)
    return text.format(**kwargs) if kwargs else text


def bundled_scripts_dir() -> Path:
    return Path(__file__).resolve().parent / "scripts" / "linux" / "v1.0"


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def _container_running(name: str = _CONTAINER_NAME) -> bool:
    if not _docker_available():
        return False
    try:
        proc = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0 and proc.stdout.strip().lower() == "true"


@dataclass(frozen=True)
class MobileStatus:
    ok: bool
    mobile_supported: bool
    setup_state: SetupState
    backend: MobileBackend
    platform: str
    reason: str
    adb_available: bool
    adb_path: str
    devices: tuple[str, ...]
    selected_device: str | None
    container_running: bool


def mobile_capabilities_enabled(config: OctopConfig) -> bool:
    return bool(config.capabilities.mobile.enabled)


def mobile_status(config: OctopConfig, *, locale: str = "en") -> MobileStatus:
    cap = config.capabilities.mobile
    system = platform.system().lower()
    adb_path = find_adb() or ""
    adb_available = bool(adb_path)
    devices = tuple(list_devices(adb=adb_path or None)) if adb_available else ()
    container_running = _container_running()

    if not cap.enabled or cap.backend == "none":
        return MobileStatus(
            ok=False,
            mobile_supported=False,
            setup_state="unsupported",
            backend="none",
            platform=system,
            reason=cap.reason or _mobile_log(locale, "unsupported_reason"),
            adb_available=adb_available,
            adb_path=adb_path,
            devices=devices,
            selected_device=devices[0] if devices else None,
            container_running=container_running,
        )

    backend: MobileBackend = cap.backend  # type: ignore[assignment]

    if backend == "physical":
        if not adb_available:
            return MobileStatus(
                ok=False,
                mobile_supported=True,
                setup_state="needs_device",
                backend=backend,
                platform=system,
                reason=_mobile_log(locale, "adb_not_found"),
                adb_available=False,
                adb_path="",
                devices=(),
                selected_device=None,
                container_running=False,
            )
        if not devices:
            return MobileStatus(
                ok=False,
                mobile_supported=True,
                setup_state="needs_device",
                backend=backend,
                platform=system,
                reason=_mobile_log(locale, "no_device"),
                adb_available=True,
                adb_path=adb_path,
                devices=(),
                selected_device=None,
                container_running=False,
            )
        return MobileStatus(
            ok=True,
            mobile_supported=True,
            setup_state="ready",
            backend=backend,
            platform=system,
            reason="",
            adb_available=True,
            adb_path=adb_path,
            devices=devices,
            selected_device=devices[0],
            container_running=False,
        )

    # Container backends (redroid / emulator)
    if not container_running:
        return MobileStatus(
            ok=False,
            mobile_supported=True,
            setup_state="needs_install",
            backend=backend,
            platform=system,
            reason="",
            adb_available=adb_available,
            adb_path=adb_path,
            devices=devices,
            selected_device=devices[0] if devices else None,
            container_running=False,
        )
    if not adb_available:
        return MobileStatus(
            ok=False,
            mobile_supported=True,
            setup_state="needs_device",
            backend=backend,
            platform=system,
            reason=_mobile_log(locale, "adb_not_found"),
            adb_available=False,
            adb_path="",
            devices=(),
            selected_device=None,
            container_running=True,
        )
    # Redroid exposes adb on the mapped host port; reconnect if the daemon
    # dropped the session (common after container restart / install restart).
    if not devices:
        adb_connect(_CONTAINER_ADB_ENDPOINT, adb=adb_path)
        devices = tuple(list_devices(adb=adb_path))
    if not devices:
        return MobileStatus(
            ok=False,
            mobile_supported=True,
            setup_state="needs_device",
            backend=backend,
            platform=system,
            reason=_mobile_log(locale, "container_no_adb"),
            adb_available=True,
            adb_path=adb_path,
            devices=(),
            selected_device=None,
            container_running=True,
        )
    return MobileStatus(
        ok=True,
        mobile_supported=True,
        setup_state="ready",
        backend=backend,
        platform=system,
        reason="",
        adb_available=True,
        adb_path=adb_path,
        devices=devices,
        selected_device=devices[0],
        container_running=True,
    )


def _sse(event: dict[str, object]) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def install_mobile_stream(*, locale: str = "en") -> AsyncIterator[str]:
    script = bundled_scripts_dir() / "install.sh"
    if not script.is_file():
        yield _sse({"log": _mobile_log(locale, "error_script_missing")})
        yield _sse({"done": False, "error": "script_missing"})
        return
    if not _docker_available():
        yield _sse({"log": _mobile_log(locale, "error_docker_missing")})
        yield _sse({"done": False, "error": "docker_missing"})
        return
    yield _sse({"log": _mobile_log(locale, "install_log_start")})
    proc = await asyncio.create_subprocess_exec(
        "bash",
        str(script),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert proc.stdout is not None
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="replace").strip()
        if text:
            yield _sse({"log": text})
    code = await proc.wait()
    if code == 0:
        yield _sse({"log": _mobile_log(locale, "install_log_ready")})
        yield _sse({"done": True})
    else:
        yield _sse(
            {"done": False, "error": _mobile_log(locale, "error_command_failed", exit_code=code)}
        )
