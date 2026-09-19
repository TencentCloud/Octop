"""FnOS packages must not claim a platform they do not ship (issue #816).

The native .fpk payload is built by ``uv pip install --target`` on an
``ubuntu-latest`` (x86_64) runner, so it contains only x86_64 binary
extensions. Declaring ``platform=all`` in the manifest let ARM64 fnOS devices
install the package successfully and then fail at first start with an
``ImportError`` on compiled dependencies (argon2-cffi-bindings, pydantic-core).

These tests pin the honest declaration so it cannot silently regress, and check
that the native launcher refuses to start on a mismatched architecture instead
of crashing inside Python.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_COMMON_SH = _REPO / "scripts" / "fnos" / "common.sh"


def _find_bash() -> str | None:
    """Locate a working bash. CI runs on Linux/Windows; skip when unusable."""
    for cand in (os.environ.get("BASH"), shutil.which("bash")):
        if cand and Path(cand).exists():
            return cand
    # Windows fallback: Git for Windows ships bash next to git.
    for cand in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
    ):
        if Path(cand).exists():
            return cand
    return None


_BASH = _find_bash()

requires_bash = pytest.mark.skipif(_BASH is None, reason="bash not available on this host")


def _manifest_value(manifest: Path, key: str) -> str:
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    raise AssertionError(f"{manifest} has no {key}= line")


@pytest.mark.parametrize("variant", ["native", "docker"])
def test_fnos_manifest_declares_x86(variant: str) -> None:
    manifest = _REPO / "fnos" / variant / "manifest"
    assert _manifest_value(manifest, "platform") == "x86", (
        f"fnos/{variant}/manifest must not claim a platform its payload does "
        "not ship; see issue #816"
    )


def test_fnos_native_launcher_guards_architecture() -> None:
    launcher = (_REPO / "fnos" / "native" / "app" / "bin" / "octop").read_text(encoding="utf-8")
    assert "octop_require_supported_arch" in launcher, (
        "fnos/native/app/bin/octop must call the architecture guard before "
        "starting Python; see issue #816"
    )


def test_common_sh_exposes_arch_guard() -> None:
    text = _COMMON_SH.read_text(encoding="utf-8")
    assert "octop_require_supported_arch()" in text


def _to_posix(p: Path) -> str:
    """Convert D:\\dir\\x to /d/dir/x so MSYS bash resolves it."""
    s = str(p).replace("\\", "/")
    if len(s) > 1 and s[1] == ":":
        s = "/" + s[0].lower() + s[2:]
    return s


def _run_arch_guard(tmp_path: Path, host_machine: str, payload_arch: str | None) -> str:
    """Source common.sh with a stubbed payload and run the guard.

    ``payload_arch`` selects which fake payload the package contains:
    ``"aarch64"`` / ``"x86_64"`` (a real ELF fixture), ``"x86_64_with_arm_marker"``
    (an x86_64 ELF plus an aarch64-named wheel directory), ``"unclassifiable"``
    (a non-ELF file whose bytes at offset 18 mimic ``e_machine``), or ``None``.
    """
    assert _BASH is not None
    appdest = tmp_path / "apps" / "octop-native"
    site_packages = appdest / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)

    if payload_arch == "unclassifiable":
        # Not an ELF at all, but the bytes at offset 18 happen to look like
        # e_machine=0x3E: that alone must not be read as "x86_64 payload".
        blob = bytearray(b"# a linker script, not an ELF file\n")
        blob[18] = 0x3E
        (site_packages / "_script.so").write_bytes(bytes(blob))
    elif payload_arch is not None:
        # Minimal ELF header: e_machine lives at offset 18 (2 bytes, LE).
        machine = {"x86_64": 0x3E, "aarch64": 0xB7, "x86_64_with_arm_marker": 0x3E}[payload_arch]
        header = bytearray(64)
        header[0:4] = b"\x7fELF"
        header[18] = machine & 0xFF
        header[19] = (machine >> 8) & 0xFF
        (site_packages / f"_fixture.cpython-312-{payload_arch}-linux-gnu.so").write_bytes(
            bytes(header)
        )
        if payload_arch == "x86_64_with_arm_marker":
            # Wheel naming carries the architecture even when the ELF is unreadable.
            (site_packages / "pkg-1.0-cp312-cp312-manylinux2014_aarch64.dist-info").mkdir()

    # `uname -m` is shadowed so the guard sees the requested host architecture,
    # independent of the machine running the test suite.
    script = (
        "set -u\n"
        f'uname() {{ printf "%s\\n" "{host_machine}"; }}\n'
        f'export TRIM_APPDEST="{_to_posix(appdest)}"\n'
        f'source "{_to_posix(_COMMON_SH)}"\n'
        "if octop_require_supported_arch >/dev/null 2>&1; then echo GUARD_OK; "
        "else echo GUARD_BLOCKED; fi\n"
    )
    proc = subprocess.run(
        [_BASH, "-c", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert proc.stdout.strip(), f"guard produced no verdict: {proc.stderr[:400]}"
    return proc.stdout.strip()


@requires_bash
def test_arch_guard_allows_aarch64_payload_on_arm_host(tmp_path: Path) -> None:
    assert _run_arch_guard(tmp_path, "aarch64", "aarch64") == "GUARD_OK"


@requires_bash
def test_arch_guard_allows_x86_64_host(tmp_path: Path) -> None:
    assert _run_arch_guard(tmp_path, "x86_64", "x86_64") == "GUARD_OK"


@requires_bash
def test_arch_guard_blocks_x86_64_payload_on_arm_host(tmp_path: Path) -> None:
    """The regression from issue #816: x86_64 payload on an ARM64 device."""
    assert _run_arch_guard(tmp_path, "aarch64", "x86_64") == "GUARD_BLOCKED"


@requires_bash
def test_arch_guard_blocks_x86_64_payload_on_arm64_host(tmp_path: Path) -> None:
    """``arm64`` is the Linux/GNU spelling of the same machine type."""
    assert _run_arch_guard(tmp_path, "arm64", "x86_64") == "GUARD_BLOCKED"


@requires_bash
def test_arch_guard_allows_empty_payload(tmp_path: Path) -> None:
    """An unexpected payload shape must not be blocked on a heuristic."""
    assert _run_arch_guard(tmp_path, "aarch64", None) == "GUARD_OK"


@requires_bash
def test_arch_guard_allows_unclassifiable_payload(tmp_path: Path) -> None:
    """A non-ELF ``.so`` must not be classified from offset 18 alone."""
    assert _run_arch_guard(tmp_path, "aarch64", "unclassifiable") == "GUARD_OK"


@requires_bash
def test_arch_guard_allows_payload_with_arm_wheel_marker(tmp_path: Path) -> None:
    """An aarch64 wheel tag is still enough evidence to let the payload through."""
    assert _run_arch_guard(tmp_path, "aarch64", "x86_64_with_arm_marker") == "GUARD_OK"
