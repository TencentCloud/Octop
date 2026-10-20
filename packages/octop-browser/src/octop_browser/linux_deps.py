"""Install Chromium OS shared libraries on Linux.

Playwright's ``install-deps`` only knows Debian/Ubuntu (it shells out to
``apt-get``). On TencentOS / OpenCloudOS / RHEL / Fedora / SUSE / Arch /
Alpine it fails with ``apt-get: command not found`` even after the
Chromium zip has already been downloaded, and verification then dies on
missing libraries such as ``libatk-bridge-2.0.so.0``.

This module detects the native package manager and installs the
equivalent shared libraries, then a CJK font package so Chromium can
render Chinese (and other CJK) text. ``playwright install-deps`` is
still used when ``apt-get`` is present (it knows Ubuntu 24 ``*t64``
package names).
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass

# Detection order: apt first (Playwright's official path), then RPM-family
# managers used by TencentOS / OpenCloudOS / RHEL, then the rest.
_MANAGERS = ("apt-get", "dnf", "yum", "zypper", "pacman", "apk")

# Conservative sets: names that exist on current stable releases.
_PACKAGES: dict[str, tuple[str, ...]] = {
    "apt-get": (
        "libnss3",
        "libnspr4",
        "libatk1.0-0",
        "libatk-bridge2.0-0",
        "libcups2",
        "libdrm2",
        "libgbm1",
        "libxkbcommon0",
        "libxcomposite1",
        "libxdamage1",
        "libxfixes3",
        "libxrandr2",
        "libasound2",
        "libpango-1.0-0",
        "libx11-6",
        "libxext6",
    ),
    "dnf": (
        "nss",
        "nspr",
        "atk",
        "at-spi2-atk",
        "cups-libs",
        "libdrm",
        "mesa-libgbm",
        "libX11",
        "libXcomposite",
        "libXdamage",
        "libXext",
        "libXfixes",
        "libXrandr",
        "libxkbcommon",
        "pango",
        "alsa-lib",
    ),
    "yum": (
        "nss",
        "nspr",
        "atk",
        "at-spi2-atk",
        "cups-libs",
        "libdrm",
        "mesa-libgbm",
        "libX11",
        "libXcomposite",
        "libXdamage",
        "libXext",
        "libXfixes",
        "libXrandr",
        "libxkbcommon",
        "pango",
        "alsa-lib",
    ),
    "zypper": (
        "mozilla-nss",
        "mozilla-nspr",
        "libatk-1_0-0",
        "libatk-bridge-2_0-0",
        "libcups2",
        "libdrm2",
        "Mesa-libgbm1",
        "libX11-6",
        "libXcomposite1",
        "libXdamage1",
        "libXext6",
        "libXfixes3",
        "libXrandr2",
        "libxkbcommon0",
        "libpango-1_0-0",
        "alsa",
    ),
    "pacman": (
        "nss",
        "nspr",
        "atk",
        "at-spi2-atk",
        "libcups",
        "libdrm",
        "mesa",
        "libx11",
        "libxcomposite",
        "libxdamage",
        "libxext",
        "libxfixes",
        "libxrandr",
        "libxkbcommon",
        "pango",
        "alsa-lib",
    ),
    "apk": (
        "nss",
        "nspr",
        "atk",
        "at-spi2-core",
        "cups-libs",
        "libdrm",
        "mesa-gbm",
        "libx11",
        "libxcomposite",
        "libxdamage",
        "libxext",
        "libxfixes",
        "libxrandr",
        "libxkbcommon",
        "pango",
        "alsa-lib",
    ),
}

# CJK fonts are a separate best-effort step: they are not required to
# start Chromium, and on RPM hosts they often live in extra repos
# (EPOL / EPEL) that may be disabled. A missing font name must never
# roll back the shared-library install.
_FONT_PACKAGES: dict[str, tuple[str, ...]] = {
    "apt-get": ("fonts-noto-cjk",),
    "dnf": (
        "google-noto-sans-cjk-ttc-fonts",
        "google-noto-cjk-fonts",
        "wqy-zenhei-fonts",
    ),
    "yum": (
        "google-noto-sans-cjk-ttc-fonts",
        "google-noto-cjk-fonts",
        "wqy-zenhei-fonts",
    ),
    "zypper": ("noto-sans-cjk-fonts",),
    "pacman": ("noto-fonts-cjk",),
    "apk": ("font-noto-cjk",),
}

_INSTALL_PREFIX: dict[str, tuple[str, ...]] = {
    "apt-get": ("apt-get", "install", "-y"),
    # --skip-unavailable keeps one missing name from aborting the rest
    # (dnf 4+; TencentOS 4 / RHEL 8+).
    "dnf": ("dnf", "install", "-y"),
    "yum": ("yum", "install", "-y"),
    "zypper": ("zypper", "--non-interactive", "install", "-y"),
    "pacman": ("pacman", "-S", "--noconfirm", "--needed"),
    "apk": ("apk", "add", "--no-cache"),
}


@dataclass(frozen=True)
class InstallStep:
    """One command in the Linux system-deps pipeline."""

    label: str
    cmd: list[str]
    env: dict[str, str] | None = None
    optional: bool = False


def detect_package_manager() -> str | None:
    """Return the first known package manager on ``PATH``, or ``None``."""
    for name in _MANAGERS:
        if shutil.which(name):
            return name
    return None


def with_privileges(cmd: list[str]) -> list[str]:
    """Prefix ``sudo -n --`` when the process is not root.

    ``-n`` never prompts; a password-required sudo fails immediately so
    dashboard / SSE installers cannot hang waiting for a TTY.
    """
    if sys.platform != "linux":
        return list(cmd)
    try:
        if os.geteuid() == 0:
            return list(cmd)
    except AttributeError:
        return list(cmd)
    sudo = shutil.which("sudo")
    if sudo is None:
        return list(cmd)
    return [sudo, "-n", "--", *cmd]


def manual_hint(manager: str | None = None) -> str:
    """Human-readable command to run when automatic install failed."""
    mgr = manager if manager is not None else detect_package_manager()
    if mgr is None or mgr not in _PACKAGES:
        return "Run: sudo playwright install-deps chromium"
    prefix = " ".join(_INSTALL_PREFIX[mgr])
    # Keep the hint short: the libraries that actually block Chrome start.
    shown = " ".join(_PACKAGES[mgr][:6])
    return f"Run: sudo {prefix} {shown} ..."


def build_install_steps(playwright_cmd: list[str]) -> list[InstallStep]:
    """Return Linux system-deps commands to try, in order.

    Library steps (required; first success wins, later library fallbacks
    are skipped):

    * Debian/Ubuntu (``apt-get``): Playwright's installer first (complete
      ``*t64`` list), then a native apt fallback.
    * Other known managers: skip Playwright (it will only print
      ``apt-get: command not found``) and install via the native tool.
    * Unknown: keep the Playwright command so behaviour matches the
      previous installer.

    Font steps (``optional=True``) always run after a library success so
    CJK text renders; a missing font package does not fail the pipeline.
    """
    manager = detect_package_manager()
    steps: list[InstallStep] = []
    if manager in (None, "apt-get"):
        steps.append(
            InstallStep(
                label="playwright install-deps",
                cmd=list(playwright_cmd),
            )
        )
    if manager is not None:
        steps.append(_native_batch_step(manager))
        steps.extend(_font_steps(manager))
    return steps


def _native_batch_step(manager: str) -> InstallStep:
    prefix = list(_INSTALL_PREFIX[manager])
    packages = list(_PACKAGES[manager])
    cmd = [*prefix, *packages]
    if manager == "apt-get":
        cmd = ["env", "DEBIAN_FRONTEND=noninteractive", *cmd]
    return InstallStep(
        label=f"{manager}",
        cmd=with_privileges(cmd),
    )


def _font_steps(manager: str) -> list[InstallStep]:
    packages = list(_FONT_PACKAGES.get(manager, ()))
    if not packages:
        return []
    # Install each font package independently and mark every step optional:
    # a single missing/unsupported package name must not abort the others.
    # We deliberately avoid dnf's --skip-unavailable flag — it only exists in
    # dnf 4+, while TencentOS 3 / RHEL 8 ship a dnf (yum-compat) that rejects
    # it with "unrecognized arguments", silently skipping all CJK fonts.
    steps: list[InstallStep] = []
    for pkg in packages:
        prefix = list(_INSTALL_PREFIX[manager])
        cmd = [*prefix, pkg]
        if manager == "apt-get":
            cmd = ["env", "DEBIAN_FRONTEND=noninteractive", *cmd]
        steps.append(
            InstallStep(
                label=f"{manager} cjk-fonts",
                cmd=with_privileges(cmd),
                optional=True,
            )
        )
    return steps
