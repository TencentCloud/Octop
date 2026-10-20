"""Chromium installer via Playwright subprocess.

Provides a programmatic ``install-browser`` interface that downloads a
Chromium binary into Playwright's standard cache directory
(``~/.cache/ms-playwright/chromium-<rev>/`` on Linux, ``$PLAYWRIGHT_BROWSERS_PATH``
when set). The location is the same one
:func:`octop_browser.cdp.launcher._find_playwright_chromium` falls back to,
so once installed the binary is automatically picked up by ``BrowserSession``.

Flavours exposed:

- :func:`chromium_executable` — locate an already-installed Playwright Chromium.
- :func:`verify_chromium` — check whether the Chromium binary actually runs.
- :func:`ensure_chromium` — synchronous install (good for CLI / scripts).
- :func:`install_chromium_stream` — async generator yielding log/done events
  (good for SSE endpoints, MCP streaming tools, dashboards).

Install pipeline (each step is best-effort; the verify step is the final
gate that decides success):

  1. ``pip install playwright`` if the package isn't importable
     (skipped when ``OCTOP_SKIP_PLAYWRIGHT_PIP=1``).
  2. ``playwright install chromium`` to download the browser binary
     (races npmmirror vs the official CDN, then falls back).
  3. Install OS shared libraries (Linux only; skipped on macOS / Windows):
     ``playwright install-deps chromium`` when ``apt-get`` is available,
     otherwise the native package manager (dnf / yum / zypper / pacman /
     apk). Then install a CJK font package so Chinese text renders.
     Needs elevated privileges; if it fails, the install still
     proceeds to verification.
  4. **Verify**: run ``chrome --version`` to confirm the binary can start.
     If verification fails (e.g. missing system library), the install is
     reported as unsuccessful with a precise error message.

Playwright is *not* a runtime dependency of octop-browser. The installer
auto-bootstraps it on first use by running ``pip install playwright`` into
the current Python environment, then drives ``python -m playwright install
chromium`` to fetch the browser binary. Set ``OCTOP_SKIP_PLAYWRIGHT_PIP=1``
to skip the pip step (e.g. when the package is provided by your image /
distro and you don't want pip to touch it).
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import importlib.util
import logging
import os
import shutil
import subprocess
import sys
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import TypedDict

from octop_browser.cdp.launcher import _find_playwright_chromium
from octop_browser.linux_deps import build_install_steps, manual_hint
from octop_browser.playwright_download import (
    build_download_candidates,
    env_for_candidate,
    plain_cli_env,
    race_download_sources,
)

logger = logging.getLogger(__name__)

__all__ = [
    "InstallEvent",
    "chromium_executable",
    "ensure_chromium",
    "install_chromium_stream",
    "verify_chromium",
]

_SKIP_PIP_ENV = "OCTOP_SKIP_PLAYWRIGHT_PIP"
#: Alternate env name, still honoured so existing deployment scripts keep working.
_SKIP_PIP_ENV_LEGACY = "HARNESS_SKIP_PLAYWRIGHT_PIP"


class InstallEvent(TypedDict, total=False):
    """One event emitted by :func:`install_chromium_stream`.

    Either ``log`` (subprocess stdout/stderr line) or terminal
    ``done``/``success`` keys are set, never both.
    """

    log: str
    done: bool
    success: bool
    error: str


def chromium_executable() -> str | None:
    """Return the path to a Playwright-managed Chromium binary, or ``None``.

    Thin wrapper around the launcher's internal lookup so callers don't
    need to reach into a private module.
    """
    return _find_playwright_chromium()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _playwright_available() -> bool:
    """Return True if the ``playwright`` package is importable.

    We probe via ``find_spec`` instead of a real import because Playwright
    is heavy and we don't want it loaded into our process unless callers
    actually need it.
    """
    # ``find_spec`` caches the module-finder result; if a previous call
    # ran before we pip-installed playwright the cache will still say
    # "not found". ``invalidate_caches`` makes the post-install check
    # see the freshly-installed package.
    importlib.invalidate_caches()
    return importlib.util.find_spec("playwright") is not None


def _skip_pip_bootstrap() -> bool:
    raw = os.environ.get(_SKIP_PIP_ENV) or os.environ.get(_SKIP_PIP_ENV_LEGACY, "")
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _pip_install_candidates() -> list[list[str]]:
    """Commands to bootstrap playwright, tried in order."""
    candidates: list[list[str]] = []
    if shutil.which("uv"):
        # Pass --python to avoid "No virtual environment found" when uv is
        # invoked outside an activated venv (e.g. from a FastAPI worker).
        candidates.append(
            ["uv", "pip", "install", "playwright", "--python", sys.executable]
        )
    candidates.append([sys.executable, "-m", "pip", "install", "playwright"])
    return candidates


def _pip_install_cmd() -> list[str]:
    return _pip_install_candidates()[0]


def _multi_pip_bootstrap_enabled() -> bool:
    raw = os.environ.get("OCTOP_MULTI_PIP_BOOTSTRAP") or os.environ.get(
        "HARNESS_MULTI_PIP_BOOTSTRAP", ""
    )
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _run_pip_install(*, quiet: bool) -> bool:
    """Try each pip bootstrap command until playwright becomes importable."""
    candidates = _pip_install_candidates()
    if not _multi_pip_bootstrap_enabled():
        candidates = candidates[:1]
    for cmd in candidates:
        try:
            result = subprocess.run(
                cmd,
                capture_output=quiet,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            logger.error("Failed to invoke %s: %s", cmd[0], exc)
            continue
        if result.returncode == 0 and _playwright_available():
            return True
        logger.info(
            "playwright bootstrap via %r failed (rc=%s)",
            cmd,
            result.returncode,
        )
    return False


def _playwright_install_cmd() -> list[str]:
    return [sys.executable, "-m", "playwright", "install", "chromium"]


def _playwright_install_deps_cmd() -> list[str]:
    return [sys.executable, "-m", "playwright", "install-deps", "chromium"]


def _run_install_deps(*, quiet: bool = True) -> bool:
    """Install Chromium OS libraries and CJK fonts (Linux only, best-effort).

    Tries Playwright's ``install-deps`` on Debian/Ubuntu, then (or
    instead, when ``apt-get`` is missing) the native package manager.
    After a library step succeeds, still runs the optional CJK font
    step — a missing font package does not fail this function.

    Returns True on success or when the step is not applicable (non-Linux).
    Returns False if every library command fails — the caller should still
    proceed to verification so a precise error can be reported.
    """
    if sys.platform not in ("linux",):
        return True
    libs_ok = False
    fonts_ok = False
    for step in build_install_steps(_playwright_install_deps_cmd()):
        if not step.optional and libs_ok:
            continue
        if step.optional and (fonts_ok or not libs_ok):
            continue
        try:
            result = subprocess.run(
                step.cmd,
                capture_output=quiet,
                text=True,
                check=False,
                env=step.env,
            )
        except FileNotFoundError:
            continue
        if result.returncode == 0:
            if step.optional:
                fonts_ok = True
            else:
                libs_ok = True
    return libs_ok


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def verify_chromium() -> tuple[bool, str]:
    """Check whether the installed Chromium binary can actually run.

    Returns ``(ok, message)`` where *ok* is ``True`` when the binary
    starts successfully, and *message* is a human-readable description
    (version string on success, diagnostic on failure).
    """
    exe = chromium_executable()
    if exe is None:
        return False, "Chromium binary not found"
    try:
        result = subprocess.run(
            [exe, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return False, "Chromium verification timed out"
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        return False, f"Chromium verification error: {exc}"

    if result.returncode == 0:
        version = result.stdout.strip()
        return True, f"Chromium {version}" if version else "Chromium OK"

    # Common on Linux: missing shared libraries (returncode 127).
    if result.returncode == 127 or "shared libraries" in result.stderr:
        lib_hint = ""
        for line in result.stderr.splitlines():
            if ".so" in line:
                lib_hint = line.strip()
                break
        hint = f": {lib_hint}" if lib_hint else ""
        return False, (
            f"Chromium binary exists but cannot start (missing system library{hint}). "
            f"{manual_hint()}"
        )

    return False, (
        f"Chromium exited with code {result.returncode}: "
        f"{result.stderr.strip() or result.stdout.strip()}"
    )


# ---------------------------------------------------------------------------
# Synchronous install
# ---------------------------------------------------------------------------


def ensure_chromium(quiet: bool = True) -> bool:
    """Install Playwright Chromium synchronously. Return ``True`` on success.

    Steps:
      1. If a Chromium binary already exists and verifies, short-circuit.
      2. ``pip install playwright`` if the package isn't importable
         (skipped when ``OCTOP_SKIP_PLAYWRIGHT_PIP=1``).
      3. ``playwright install chromium`` to download the binary
         (races npmmirror vs official CDN).
      4. Install OS shared libraries and CJK fonts (Linux only, best-effort):
         Playwright ``install-deps`` on Debian/Ubuntu, otherwise dnf/yum/zypper/…
      5. Verify the binary actually starts.
    """
    # Fast path: binary exists and runs.
    existing = chromium_executable()
    if existing:
        ok, msg = verify_chromium()
        if ok:
            if not quiet:
                print(f"Chromium already installed: {existing}")
            return True
        # Binary exists but broken — try install-deps, then re-verify.
        if not quiet:
            print(f"Chromium binary found but broken: {msg}", file=sys.stderr)
            print("Attempting to install system dependencies ...", file=sys.stderr)
        _run_install_deps(quiet=quiet)
        ok, msg = verify_chromium()
        if ok:
            if not quiet:
                print("System dependencies installed successfully.")
            return True
        if not quiet:
            print(msg, file=sys.stderr)
        return False

    # Full install pipeline.
    if not _playwright_available():
        if _skip_pip_bootstrap():
            msg = (
                "Playwright is not installed and OCTOP_SKIP_PLAYWRIGHT_PIP is set; "
                "install it manually (`pip install playwright`) and retry."
            )
            if not quiet:
                print(msg, file=sys.stderr)
            logger.error(msg)
            return False
        if not quiet:
            print("Installing playwright package via pip ...")
        if not _run_pip_install(quiet=quiet):
            logger.error("playwright bootstrap failed")
            return False

    ordered = race_download_sources(build_download_candidates())
    downloaded = False
    for cand in ordered:
        if not quiet:
            host = cand.host or "cdn.playwright.dev"
            print(f"Downloading Chromium via {cand.kind} ({host}) ...")
        try:
            result = subprocess.run(
                _playwright_install_cmd(),
                capture_output=quiet,
                text=True,
                check=False,
                env=env_for_candidate(cand),
            )
        except FileNotFoundError as exc:
            logger.error("Failed to invoke playwright installer: %s", exc)
            return False
        if result.returncode == 0:
            downloaded = True
            break
        logger.warning(
            "Playwright download via %s failed (rc=%s)",
            cand.kind,
            result.returncode,
        )
    if not downloaded:
        return False

    # Install system dependencies (Linux, best-effort).
    _run_install_deps(quiet=quiet)

    # Verify.
    ok, msg = verify_chromium()
    if not ok:
        if not quiet:
            print(msg, file=sys.stderr)
        logger.error("Chromium verification failed: %s", msg)
    return ok


# ---------------------------------------------------------------------------
# Streaming subprocess helper
# ---------------------------------------------------------------------------


async def _stream_subprocess(
    cmd: list[str],
    *,
    is_disconnected: Callable[[], bool | Awaitable[bool]] | None,
    env: dict[str, str] | None = None,
) -> AsyncGenerator[InstallEvent, None]:
    """Run *cmd* and yield ``{log: ...}`` per output line, then ``{done, success}``."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=plain_cli_env(env),
        )
    except FileNotFoundError as exc:
        msg = f"Failed to invoke {' '.join(cmd[:3])}: {exc}"
        logger.error(msg)
        yield {"log": msg, "error": str(exc)}
        yield {"done": True, "success": False, "error": str(exc)}
        return

    assert proc.stdout is not None
    try:
        while True:
            if is_disconnected is not None:
                disconnected = is_disconnected()
                if asyncio.iscoroutine(disconnected):
                    disconnected = await disconnected
                if disconnected:
                    proc.kill()
                    break
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip("\n")
            yield {"log": text}

        returncode = await proc.wait()
        yield {"done": True, "success": returncode == 0}
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Install stream error: %s", exc)
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        yield {"done": True, "success": False, "error": str(exc)}


async def _stream_install_deps(
    *,
    is_disconnected: Callable[[], bool | Awaitable[bool]] | None,
) -> AsyncGenerator[InstallEvent, None]:
    """Stream Linux system-deps installers; last event is ``done``.

    Non-Linux callers get an immediate success. Library failure of every
    required step is reported as ``done/success=False`` with a
    distro-specific hint — the caller still proceeds to
    ``verify_chromium``. Optional CJK font steps run after a library
    success and never flip the result to failure.
    """
    if sys.platform != "linux":
        yield {"done": True, "success": True}
        return

    steps = build_install_steps(_playwright_install_deps_cmd())
    if not steps:
        yield {"log": f"No package manager detected. {manual_hint()}"}
        yield {"done": True, "success": False}
        return

    libs_ok = False
    fonts_ok = False
    for index, step in enumerate(steps):
        if not step.optional and libs_ok:
            continue
        if step.optional and (fonts_ok or not libs_ok):
            continue
        kind = "CJK fonts" if step.optional else "system dependencies"
        yield {"log": f"Installing {kind} via {step.label} ..."}
        step_ok = False
        async for event in _stream_subprocess(
            step.cmd, is_disconnected=is_disconnected, env=step.env
        ):
            if event.get("done"):
                step_ok = bool(event.get("success"))
            else:
                yield event
        if step_ok:
            if step.optional:
                fonts_ok = True
            else:
                libs_ok = True
            continue
        remaining_required = any(not later.optional for later in steps[index + 1 :])
        if not step.optional and remaining_required:
            yield {"log": f"{step.label} failed; trying native package manager ..."}

    if libs_ok:
        yield {"log": "System dependencies installed."}
        yield {"done": True, "success": True}
        return

    yield {"log": f"System deps installation failed. {manual_hint()}"}
    yield {"done": True, "success": False}


# ---------------------------------------------------------------------------
# Streaming install
# ---------------------------------------------------------------------------


async def install_chromium_stream(
    *,
    is_disconnected: Callable[[], bool | Awaitable[bool]] | None = None,
) -> AsyncGenerator[InstallEvent, None]:
    """Stream the install pipeline as structured events.

    Pipeline (each step yields its own ``log`` lines; only the final step
    emits a terminal ``done`` event):

      1. If a binary already exists and verifies, short-circuit.
      2. ``pip install playwright`` if the package isn't importable
         (skipped when ``OCTOP_SKIP_PLAYWRIGHT_PIP=1``).
      3. ``playwright install chromium`` to fetch the browser binary
         (races npmmirror vs official CDN).
      4. Install OS shared libraries and CJK fonts (Linux only, best-effort
         — failure does not block the pipeline). Uses Playwright
         ``install-deps`` when ``apt-get`` is present, otherwise
         dnf/yum/zypper/pacman/apk.
      5. **Verify**: run ``chrome --version`` to confirm the binary works.

    Args:
        is_disconnected: Optional callable returning ``True`` to signal
            that the consumer has disconnected. Subprocesses are killed
            on disconnect.
    """
    # Fast path: binary exists and verifies.
    existing = chromium_executable()
    if existing:
        ok, msg = await asyncio.to_thread(verify_chromium)
        if ok:
            yield {"log": f"Chromium already installed: {existing}"}
            yield {"done": True, "success": True}
            return
        # Binary exists but broken — try install-deps then re-verify.
        yield {"log": f"Chromium binary found but broken: {msg}"}
        if sys.platform == "linux":
            yield {"log": "Attempting to install system dependencies ..."}
            async for event in _stream_install_deps(is_disconnected=is_disconnected):
                if event.get("done"):
                    continue
                yield event
        # Re-verify after install-deps.
        ok, msg = await asyncio.to_thread(verify_chromium)
        if ok:
            yield {"log": f"Chromium verified: {msg}"}
            yield {"done": True, "success": True}
            return
        # Still broken — fall through to full download pipeline.
        yield {"log": "Still broken after install-deps; re-downloading Chromium ..."}

    # Step: pip install playwright (if needed).
    if not _playwright_available():
        if _skip_pip_bootstrap():
            msg = (
                "Playwright is not installed and OCTOP_SKIP_PLAYWRIGHT_PIP is set; "
                "install it manually (`pip install playwright`) and retry."
            )
            yield {"log": msg, "error": msg}
            yield {"done": True, "success": False, "error": msg}
            return

        yield {"log": "Installing playwright package ..."}
        pip_success = False
        candidates = _pip_install_candidates()
        if not _multi_pip_bootstrap_enabled():
            candidates = candidates[:1]
        last_error = ""
        for cmd in candidates:
            yield {"log": f"Trying: {' '.join(cmd)}"}
            async for event in _stream_subprocess(cmd, is_disconnected=is_disconnected):
                if event.get("done"):
                    if event.get("success") and _playwright_available():
                        pip_success = True
                        break
                    if event.get("error"):
                        last_error = str(event["error"])
                else:
                    yield event
            if pip_success:
                break

        if not pip_success or not _playwright_available():
            err = last_error or "playwright package install failed"
            yield {"log": err, "error": err}
            yield {"done": True, "success": False, "error": err}
            return

    # Step: download Chromium binary (race mirrors, then fall back).
    yield {"log": "Downloading Chromium ..."}
    ordered = await asyncio.to_thread(
        race_download_sources, build_download_candidates()
    )
    if ordered:
        yield {"log": f"Playwright CDN race winner={ordered[0].kind}"}
    download_ok = False
    last_error = "Chromium download failed"
    for index, cand in enumerate(ordered):
        host = cand.host or "cdn.playwright.dev"
        yield {"log": f"Trying Playwright source: {cand.kind} ({host})"}
        async for event in _stream_subprocess(
            _playwright_install_cmd(),
            is_disconnected=is_disconnected,
            env=env_for_candidate(cand),
        ):
            if event.get("done"):
                download_ok = bool(event.get("success"))
                if event.get("error"):
                    last_error = str(event["error"])
            else:
                yield event
        if download_ok:
            break
        if index + 1 < len(ordered):
            yield {"log": (f"Download via {cand.kind} failed; trying next source...")}
    if not download_ok:
        yield {"done": True, "success": False, "error": last_error}
        return

    # Step: install system dependencies (Linux only, best-effort).
    if sys.platform == "linux":
        yield {"log": "Installing system dependencies ..."}
        async for event in _stream_install_deps(is_disconnected=is_disconnected):
            if event.get("done"):
                continue
            yield event

    # Step: verify.
    yield {"log": "Verifying installation ..."}
    ok, msg = await asyncio.to_thread(verify_chromium)
    if ok:
        yield {"log": msg}
        yield {"done": True, "success": True}
    else:
        yield {"log": msg, "error": msg}
        yield {"done": True, "success": False, "error": msg}


def _have_npx() -> bool:
    """Test helper; kept for symmetry with finnie's installer probes."""
    return shutil.which("npx") is not None
