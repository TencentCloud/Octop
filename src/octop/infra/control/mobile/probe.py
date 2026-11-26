"""Install-time host capability detection for Remote Android."""

from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

MobileBackend = Literal["physical", "redroid", "emulator", "none"]


@dataclass(frozen=True)
class MobileProbeResult:
    enabled: bool
    backend: MobileBackend
    reason: str
    probed_at: str


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def linux_binder_available() -> bool:
    if Path("/dev/binder").exists():
        return True
    modules = Path("/proc/modules")
    if modules.is_file():
        try:
            text = modules.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        if "binder_linux" in text:
            return True
    try:
        proc = subprocess.run(
            ["lsmod"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "binder_linux" in (proc.stdout or "")


def kvm_available() -> bool:
    return Path("/dev/kvm").exists()


def physical_device_available() -> bool:
    """True when adb lists a real device (USB or wireless), not an emulator.

    Container endpoints on localhost are skipped: they are the redroid/emulator
    backend, not a phone the user plugged in. A device in the ``unauthorized``
    state still counts: the phone is attached and only needs the USB-debug
    prompt accepted (#3084).
    """
    from octop.infra.control.mobile.adb import (  # noqa: PLC0415
        find_adb,
        is_emulator_device,
        list_device_states,
    )

    adb = find_adb()
    if not adb:
        return False
    try:
        states = list_device_states(adb=adb)
    except Exception:
        return False
    for device, state in states.items():
        if device.startswith(("127.0.0.1:", "localhost:")):
            continue
        if state == "unauthorized":
            return True
        if state != "device":
            continue
        try:
            if not is_emulator_device(device, adb=adb):
                return True
        except Exception:
            continue
    return False


def probe_host_capability(*, probed_at: str | None = None) -> MobileProbeResult:
    """Detect whether this host can run Remote Android and which backend applies."""
    when = probed_at or utc_now_iso()
    system = platform.system()
    if system in {"Darwin", "Windows"}:
        return MobileProbeResult(True, "physical", "", when)
    if system == "Linux":
        # A physical phone must win over KVM/binder, otherwise a Linux desktop
        # with virtualization enabled is always classified as an emulator host
        # and the connected device is ignored (#3084).
        if physical_device_available():
            return MobileProbeResult(True, "physical", "", when)
        if linux_binder_available():
            return MobileProbeResult(True, "redroid", "", when)
        if kvm_available():
            return MobileProbeResult(True, "emulator", "", when)
        return MobileProbeResult(False, "none", "no_binder_or_kvm", when)
    return MobileProbeResult(
        False,
        "none",
        f"unsupported_platform:{system.lower()}",
        when,
    )
