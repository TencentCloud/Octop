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


def probe_host_capability(*, probed_at: str | None = None) -> MobileProbeResult:
    """Detect whether this host can run Remote Android and which backend applies."""
    when = probed_at or utc_now_iso()
    system = platform.system()
    if system in {"Darwin", "Windows"}:
        return MobileProbeResult(True, "physical", "", when)
    if system == "Linux":
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
