"""Chrome process management: launch, attach, and discover."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import IO, Any

import aiohttp

from octop_browser.profile import Profile

logger = logging.getLogger(__name__)

_CHROME_PATHS_LINUX = [
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
    "/snap/bin/chromium",
]

_CHROME_PATHS_MAC = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]

# Windows installs are keyed off env vars because the drive letter and the
# "Program Files (x86)" spelling are localised / configurable.
_CHROME_SUFFIXES_WIN = [
    ("Google", "Chrome", "Application", "chrome.exe"),
    ("Chromium", "Application", "chrome.exe"),
    ("Microsoft", "Edge", "Application", "msedge.exe"),
]

# Linux clone flag for creating a new user namespace; used by
# ``_user_namespaces_available()`` to probe whether Chrome's zygote will
# be allowed to start.
_CLONE_NEWUSER = 0x10000000


def _playwright_exe_candidates(cdir: Path) -> list[Path]:
    """Return the binary locations Playwright has used inside ``chromium-<rev>/``.

    Playwright moved its Chromium builds to Chrome for Testing, which renamed
    the per-platform directory (``chrome-win`` → ``chrome-win64``,
    ``chrome-mac`` → ``chrome-mac-<arch>``) and the macOS bundle. Newer
    layouts are probed first, legacy ones kept so older installs still work.
    """
    if sys.platform == "darwin":
        cft = (
            "Google Chrome for Testing.app",
            "Contents",
            "MacOS",
            "Google Chrome for Testing",
        )
        return [
            cdir.joinpath("chrome-mac-arm64", *cft),
            cdir.joinpath("chrome-mac-x64", *cft),
            cdir.joinpath(
                "chrome-mac", "Chromium.app", "Contents", "MacOS", "Chromium"
            ),
        ]
    if sys.platform.startswith("win"):
        return [
            cdir / "chrome-win64" / "chrome.exe",
            cdir / "chrome-win" / "chrome.exe",
        ]
    return [
        cdir / "chrome-linux64" / "chrome",
        cdir / "chrome-linux" / "chrome",
    ]


def _find_playwright_chromium() -> str | None:
    """Locate a Chromium binary previously downloaded by Playwright.

    Playwright stores browsers under ``$PLAYWRIGHT_BROWSERS_PATH`` (when set)
    or ``~/.cache/ms-playwright`` on Linux, ``~/Library/Caches/ms-playwright``
    on macOS, and ``%USERPROFILE%\\AppData\\Local\\ms-playwright`` on Windows.
    Inside that root each browser revision lives at ``chromium-<rev>/``; see
    :func:`_playwright_exe_candidates` for the layouts probed within it. We
    pick the highest-numbered revision so a freshly-installed Playwright
    build wins automatically.
    """
    env_root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    candidates: list[Path] = []
    if env_root:
        candidates.append(Path(env_root))
    if sys.platform == "darwin":
        candidates.append(Path.home() / "Library" / "Caches" / "ms-playwright")
    elif sys.platform.startswith("win"):
        local = os.environ.get("LOCALAPPDATA")
        if local:
            candidates.append(Path(local) / "ms-playwright")
    else:
        candidates.append(Path.home() / ".cache" / "ms-playwright")

    for root in candidates:
        if not root.is_dir():
            continue
        # chromium-<rev> directories; sort numerically by revision so we
        # pick the newest install.
        chromium_dirs = sorted(
            (p for p in root.glob("chromium-*") if p.is_dir()),
            key=lambda p: _parse_pw_revision(p.name),
            reverse=True,
        )
        for cdir in chromium_dirs:
            for exe in _playwright_exe_candidates(cdir):
                if exe.exists():
                    logger.debug("Found Playwright Chromium at %s", exe)
                    return str(exe)
    return None


def _parse_pw_revision(name: str) -> int:
    """Parse a ``chromium-<rev>`` directory name into an int for sorting."""
    suffix = name.rsplit("-", 1)[-1]
    try:
        return int(suffix)
    except ValueError:
        return -1


def _chrome_paths_win() -> list[str]:
    """Standard Chrome / Chromium / Edge locations on Windows."""
    roots = [
        os.environ.get("PROGRAMFILES"),
        os.environ.get("PROGRAMFILES(X86)"),
        os.environ.get("LOCALAPPDATA"),
    ]
    return [
        str(Path(root).joinpath(*suffix))
        for suffix in _CHROME_SUFFIXES_WIN
        for root in roots
        if root
    ]


def find_chrome() -> str | None:
    """Return the path to the first available Chrome/Chromium executable.

    Search order:
      1. ``BROWSER_USE_CHROME_BIN`` (explicit override)
      2. Standard system install paths (``/usr/bin/google-chrome``,
         ``%PROGRAMFILES%\\Google\\Chrome\\Application\\chrome.exe``, …)
      3. ``PATH`` lookup for ``google-chrome`` / ``chromium`` / ``chrome.exe`` / …
      4. Playwright's downloaded Chromium under ``~/.cache/ms-playwright``
         (or ``$PLAYWRIGHT_BROWSERS_PATH``)
    """
    from octop_browser.settings import settings as _settings

    if _settings.chrome_bin and Path(_settings.chrome_bin).exists():
        return _settings.chrome_bin
    if sys.platform == "darwin":
        candidates = _CHROME_PATHS_MAC
    elif sys.platform.startswith("win"):
        candidates = _chrome_paths_win()
    else:
        candidates = _CHROME_PATHS_LINUX
    for path in candidates:
        if Path(path).exists():
            return path
    # PATH lookup
    if sys.platform.startswith("win"):
        on_path = shutil.which("chrome") or shutil.which("msedge")
    else:
        on_path = (
            shutil.which("google-chrome")
            or shutil.which("chromium")
            or shutil.which("chromium-browser")
        )
    if on_path:
        return on_path
    # Last resort: Playwright's bundled Chromium (common on dev machines and
    # in projects that already depend on Playwright).
    return _find_playwright_chromium()


def _build_flags(profile: Profile, headless: bool) -> list[str]:
    from octop_browser.settings import settings as _settings

    flags = [
        f"--remote-debugging-port={profile.cdp_port}",
        f"--user-data-dir={profile.data_dir}",
        "--disable-background-networking",
        "--disable-sync",
        "--disable-translate",
        "--disable-extensions",
        "--disable-default-apps",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-popup-blocking",
        "--metrics-recording-only",
        "--safebrowsing-disable-auto-update",
        # Chrome >=128 hardened its crashpad handler to require an explicit
        # ``--database`` path; in containers/root/CI environments where the
        # crash-database directory can't be resolved (missing/unwritable
        # HOME, no XDG dirs, etc.) the handler subprocess aborts with
        # "chrome_crashpad_handler: --database is required" and takes the
        # whole browser down with it (exits before binding the CDP port).
        # We don't need crash reporting here, so disable it outright rather
        # than depending on crashpad's directory resolution succeeding.
        "--disable-crash-reporter",
        "--disable-breakpad",
    ]
    # If user is binding Chrome to a non-loopback host (e.g. for Docker port
    # forwarding), pass --remote-debugging-address so Chrome listens externally.
    if _settings.cdp_host not in ("localhost", "127.0.0.1"):
        flags.append(f"--remote-debugging-address={_settings.cdp_host}")
    if headless:
        flags.append("--headless=new")
    if _should_disable_sandbox():
        flags.append("--no-sandbox")
    # GPU + /dev/shm: in containerised / GPU-less environments Chrome's GPU
    # process aborts (SwiftShader's CreateCommandBuffer fails) and renderers
    # never start, leaving Page.enable hung. Defaults match Playwright.
    if _should_disable_gpu(headless):
        flags.append("--disable-gpu")
    if _should_disable_dev_shm():
        flags.append("--disable-dev-shm-usage")
    return flags


def _env_tristate(name: str) -> bool | None:
    """Parse a three-state boolean env var.

    Returns True for "1"/"true"/"yes"/"on", False for "0"/"false"/"no"/"off"
    (case-insensitive), and None if the variable is unset or unrecognised.
    """
    raw = os.environ.get(name)
    if raw is None:
        return None
    v = raw.strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return None


def _should_disable_gpu(headless: bool) -> bool:
    """Return True if Chrome should be launched with ``--disable-gpu``.

    Default: True in headless mode (containers / SSH sessions rarely have a
    working GPU; SwiftShader's command buffer is fragile and can crash the
    GPU process), False in headed mode (the user has a desktop and likely
    wants hardware acceleration).

    ``BROWSER_USE_DISABLE_GPU=1`` forces it on regardless of mode;
    ``BROWSER_USE_DISABLE_GPU=0`` forces it off.
    """
    override = _env_tristate("BROWSER_USE_DISABLE_GPU")
    if override is not None:
        return override
    return headless


def _should_disable_dev_shm() -> bool:
    """Return True if Chrome should be launched with ``--disable-dev-shm-usage``.

    Default: True on Linux (Docker's default ``/dev/shm`` is 64 MiB which is
    too small for Chrome's renderer shared-memory regions), False elsewhere.

    ``BROWSER_USE_DISABLE_DEV_SHM_USAGE=1`` / ``=0`` overrides the default.
    """
    override = _env_tristate("BROWSER_USE_DISABLE_DEV_SHM_USAGE")
    if override is not None:
        return override
    return sys.platform.startswith("linux")


def _should_disable_sandbox() -> bool:
    """Return True if Chromium should be launched with ``--no-sandbox``.

    Chromium uses Linux user namespaces to isolate renderer processes. In
    containers / chroots / restricted sandboxes that don't grant the
    ``CLONE_NEWUSER`` capability, the zygote crashes with
    ``Failed to move to new namespace: ... Operation not permitted``
    and Chrome never binds to the CDP port.

    The flag is needed when:
      * running as root (the kernel itself rejects user-ns + setuid), OR
      * ``BROWSER_USE_NO_SANDBOX`` is truthy in the environment, OR
      * we're on Linux and a quick probe shows the kernel won't allow
        unprivileged user namespaces.

    Set ``BROWSER_USE_NO_SANDBOX=0`` to force-disable this auto-detection
    (e.g. on a hardened production host where you've already arranged
    the right caps and want Chrome's full sandbox).
    """
    override = os.environ.get("BROWSER_USE_NO_SANDBOX")
    if override is not None:
        return override.strip().lower() in ("1", "true", "yes", "on")
    if not sys.platform.startswith("linux"):
        return False
    if os.getuid() == 0:
        return True
    return not _user_namespaces_available()


_USER_NS_CACHE: bool | None = None


def _user_namespaces_available() -> bool:
    """Best-effort probe: can this process create unprivileged user namespaces?

    Direct probe: spawn a fresh ``python -c ...`` that calls
    ``unshare(CLONE_NEWUSER)`` via ctypes; if it returns -EPERM (or any
    non-zero), Chrome's zygote will fail too and we should add
    ``--no-sandbox``.

    We use ``subprocess`` rather than ``os.fork()`` because Python 3.12
    raises a DeprecationWarning when fork() is called from a process that
    has imported any threading-using module (covers most asyncio servers).
    The result is cached for the process lifetime — kernel namespace
    policy doesn't change at runtime.
    """
    global _USER_NS_CACHE
    if _USER_NS_CACHE is not None:
        return _USER_NS_CACHE
    code = (
        "import ctypes, sys; "
        "libc = ctypes.CDLL('libc.so.6', use_errno=True); "
        f"sys.exit(0 if libc.unshare({_CLONE_NEWUSER}) == 0 else 1)"
    )
    try:
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", code],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2.0,
        )
        _USER_NS_CACHE = result.returncode == 0
    except Exception:  # pylint: disable=broad-except
        _USER_NS_CACHE = False
    return _USER_NS_CACHE


async def _get_ws_url(
    port: int,
    retries: int | None = None,
    delay: float | None = None,
    *,
    process: subprocess.Popen[bytes] | None = None,
    stderr_file: IO[bytes] | None = None,
) -> str:
    """Poll Chrome's /json/version endpoint until it responds.

    When ``process`` is provided, the loop also checks ``process.poll()`` on
    each iteration; if Chrome has already exited (e.g. missing libraries,
    sandbox crash, no DISPLAY) we raise immediately with the captured
    ``stderr_file`` tail instead of waiting for the full retry budget.
    """
    from octop_browser.settings import settings as _settings

    _retries = retries if retries is not None else _settings.launch_retries
    _delay = delay if delay is not None else _settings.launch_delay
    url = f"http://{_settings.cdp_host}:{port}/json/version"
    for attempt in range(_retries):
        # Fast-fail: Chrome subprocess already exited. Surface its stderr so
        # callers see the real cause (missing libs, --no-sandbox needed, …)
        # rather than a generic "did not start after N attempts" timeout.
        if process is not None and process.poll() is not None:
            tail = _tail_stderr(stderr_file)
            detail = f"\nChrome stderr (tail):\n{tail}" if tail else ""
            raise RuntimeError(
                f"Chrome exited immediately (returncode={process.returncode}) "
                f"before binding to {_settings.cdp_host}:{port}.{detail}"
            )
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=2)
                ) as resp:
                    data = await resp.json(content_type=None)
                    ws_url: str = data["webSocketDebuggerUrl"]
                    logger.debug("Chrome ready at %s", ws_url)
                    return ws_url
        except Exception:  # noqa: BLE001  # pylint: disable=broad-except
            if attempt < _retries - 1:
                await asyncio.sleep(_delay)
    tail = _tail_stderr(stderr_file)
    detail = f"\nChrome stderr (tail):\n{tail}" if tail else ""
    raise RuntimeError(
        f"Chrome did not start on {_settings.cdp_host}:{port} "
        f"after {_retries} attempts.{detail}"
    )


def _tail_stderr(stderr_file: IO[bytes] | None, max_bytes: int = 4096) -> str:
    """Return the captured Chrome stderr (tail, decoded), or ``""`` on error.

    Best-effort: any failure (closed fd, decode error, …) yields ``""`` so
    error reporting never masks the underlying RuntimeError.
    """
    if stderr_file is None:
        return ""
    try:
        stderr_file.seek(0)
        raw = stderr_file.read()
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        if len(text) > max_bytes:
            text = "...(truncated)\n" + text[-max_bytes:]
        return text.strip()
    except Exception:  # pylint: disable=broad-except
        return ""


async def _port_in_use_at(host: str, port: int) -> bool:
    authority = f"[{host}]" if ":" in host and not host.startswith("[") else host
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"http://{authority}:{port}/json/version",
                timeout=aiohttp.ClientTimeout(total=1),
            ) as resp:
                return resp.status == 200
    except Exception:  # noqa: BLE001  # pylint: disable=broad-except
        return False


async def _port_in_use(port: int) -> bool:
    """Check if Chrome is already listening on the given port."""
    from octop_browser.settings import settings as _settings

    return await _port_in_use_at(_settings.cdp_host, port)


async def terminate_browser(
    profile: Profile,
    *,
    cdp_host: str = "localhost",
    timeout: float = 3.0,
) -> bool:
    """Stop the local Chrome instance serving ``profile``.

    Prefer CDP's graceful ``Browser.close`` so the operation is precise and
    cross-platform. The existing user-data-dir process kill remains a POSIX
    fallback for an unresponsive browser.
    """
    if cdp_host not in {"localhost", "127.0.0.1", "::1"}:
        return False
    if not await _port_in_use_at(cdp_host, profile.cdp_port):
        return False

    authority = (
        f"[{cdp_host}]"
        if ":" in cdp_host and not cdp_host.startswith("[")
        else cdp_host
    )
    version_url = f"http://{authority}:{profile.cdp_port}/json/version"
    try:
        client_timeout = aiohttp.ClientTimeout(total=2)
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.get(version_url) as resp:
                payload = await resp.json(content_type=None)
            ws_url = payload.get("webSocketDebuggerUrl")
            if ws_url:
                async with session.ws_connect(str(ws_url)) as ws:
                    await ws.send_json({"id": 1, "method": "Browser.close"})
    except Exception:  # noqa: BLE001  # pylint: disable=broad-except
        logger.debug(
            "Graceful browser close failed for profile %s",
            profile.name,
            exc_info=True,
        )

    deadline = asyncio.get_running_loop().time() + max(timeout, 0.0)
    while asyncio.get_running_loop().time() < deadline:
        if not await _port_in_use_at(cdp_host, profile.cdp_port):
            return True
        await asyncio.sleep(0.1)

    from octop_browser.cdp.launch_prep import (  # noqa: PLC0415
        clear_profile_locks,
        pkill_chrome_profile,
    )

    killed = await asyncio.to_thread(pkill_chrome_profile, profile.data_dir)
    if killed:
        await asyncio.sleep(0.1)
        await asyncio.to_thread(clear_profile_locks, profile.data_dir)
    return killed or not await _port_in_use_at(cdp_host, profile.cdp_port)


async def launch_or_attach(profile: Profile, headless: bool = False) -> str:
    """
    Ensure Chrome is running for this profile and return a CDP WebSocket URL.

    If Chrome is already running on the profile's CDP port, re-attach.
    Otherwise, launch a new Chrome process.

    Returns the browser-level WebSocket URL.
    """
    from octop_browser.settings import settings as _settings

    if await _port_in_use(profile.cdp_port):
        logger.debug(
            "Attaching to existing Chrome on %s:%d",
            _settings.cdp_host,
            profile.cdp_port,
        )
        return await _get_ws_url(profile.cdp_port)

    # Refuse to "launch" a remote browser — only local hosts can spawn Chrome.
    if _settings.cdp_host not in ("localhost", "127.0.0.1"):
        raise RuntimeError(
            f"Cannot launch Chrome on remote host '{_settings.cdp_host}'. "
            "Start Chrome there manually with --remote-debugging-port and "
            "--remote-debugging-address=0.0.0.0, or set BROWSER_USE_CDP_WS_URL "
            "to connect directly."
        )

    chrome = find_chrome()
    if chrome is None:
        raise RuntimeError(
            "Chrome/Chromium not found. Install Google Chrome or Chromium.\n"
            "On Ubuntu: sudo apt install chromium-browser\n"
            "On macOS: brew install --cask google-chrome"
        )

    # Self-heal XDG_RUNTIME_DIR / SingletonLock / unwritable profiles before
    # spawn. Must pass ``env`` explicitly — relying on inherited os.environ is
    # not enough when wrappers or host agents ignore a late parent export.
    from octop_browser.cdp.launch_prep import (  # noqa: PLC0415
        prepare_chrome_launch,
        recover_profile,
    )

    profile, chrome_env = prepare_chrome_launch(profile)
    flags = _build_flags(profile, headless=headless)
    cmd = [chrome, *flags, "about:blank"]
    logger.debug("Launching Chrome: %s", " ".join(cmd))
    # Capture Chrome's stderr to an unlinked tmpfile during the launch window
    # so missing-library / sandbox-crash / no-DISPLAY errors surface in the
    # RuntimeError instead of being silently dropped to /dev/null.
    #
    # Note: after this function returns, we close the parent's handle but
    # Chrome retains its dup'd fd. On POSIX the inode is unlinked and grows
    # over Chrome's lifetime; space is reclaimed when Chrome exits. The
    # trade-off (a few KB-MB of unlinked stderr per session) buys actionable
    # error messages on launch failure.
    stderr_file = tempfile.TemporaryFile(prefix="octop-browser-chrome-", suffix=".log")
    # Detach Chrome from our process group so it survives a short-lived
    # parent (e.g. ``octop-browser navigate ...`` exiting). Without this
    # the CLI's TTY would deliver SIGHUP/SIGINT to the whole group on exit
    # and Chrome would die — making CLI invocations effectively single-shot
    # and breaking cross-process session continuity.
    #
    # However, on macOS in headed mode we do NOT set start_new_session,
    # because creating a new session group prevents the Chrome window from
    # receiving foreground focus (the window opens but stays hidden behind
    # the launching app). On Linux/Windows the effect is less pronounced
    # so we keep the detachment there.
    popen_kwargs: dict[str, Any] = {
        "stdout": subprocess.DEVNULL,
        "stderr": stderr_file,
        "stdin": subprocess.DEVNULL,
        "env": chrome_env,
    }
    if hasattr(os, "setsid"):
        # On macOS, only detach in headless mode to keep the visible
        # Chrome window foregrounded when running headed.
        if sys.platform != "darwin" or headless:
            popen_kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen(cmd, **popen_kwargs)  # noqa: S603
        try:
            return await _get_ws_url(
                profile.cdp_port, process=proc, stderr_file=stderr_file
            )
        except RuntimeError as exc:
            msg = str(exc)
            if (
                "returncode=21" not in msg
                and "ProcessSingleton" not in msg
                and "SingletonLock" not in msg
            ):
                raise
            logger.warning(
                "Chrome launch failed for profile %s (%s); recovering and retrying",
                profile.name,
                exc,
            )
            with contextlib.suppress(Exception):
                if proc.poll() is None:
                    proc.kill()
            profile = recover_profile(profile)
            profile, chrome_env = prepare_chrome_launch(profile)
            flags = _build_flags(profile, headless=headless)
            cmd = [chrome, *flags, "about:blank"]
            popen_kwargs["env"] = chrome_env
            # Fresh stderr capture for the retry attempt.
            stderr_file.close()
            stderr_file = tempfile.TemporaryFile(
                prefix="octop-browser-chrome-", suffix=".log"
            )
            popen_kwargs["stderr"] = stderr_file
            proc = subprocess.Popen(cmd, **popen_kwargs)  # noqa: S603
            return await _get_ws_url(
                profile.cdp_port, process=proc, stderr_file=stderr_file
            )
    finally:
        stderr_file.close()


async def get_page_ws_url(port: int, profile: Profile | None = None) -> str:
    """Return the WebSocket URL of a usable page/tab.

    Selection rules (in priority order):
      1. The target id stored on *profile* (set by a previous session) if
         that target is still alive — this preserves cross-process
         continuity between CLI invocations.
      2. The first non-``about:blank`` page target — Chrome typically
         keeps an idle ``about:blank`` around even after the user has
         navigated elsewhere, so picking the first page blindly often
         attaches to the wrong tab.
      3. Any page target.
      4. If Chrome is listening but exposes no page target (possible after
         users close the last tab/window), create a fresh ``about:blank``
         target through CDP's HTTP endpoint and attach to it.

    The chosen target id is written back to *profile* so subsequent
    attaches stay sticky.
    """
    from octop_browser.settings import settings as _settings

    async with aiohttp.ClientSession() as session:
        pages = await _list_page_targets(session, _settings.cdp_host, port)
        if not pages:
            created = await _create_blank_page_target(session, _settings.cdp_host, port)
            if created is not None:
                pages = [created]
            else:
                pages = await _list_page_targets(session, _settings.cdp_host, port)

    if not pages:
        raise RuntimeError("No open page found in Chrome")

    chosen: dict[str, Any] | None = None
    if profile is not None:
        sticky_id = profile.load_target()
        if sticky_id:
            chosen = next((t for t in pages if t.get("id") == sticky_id), None)
            if chosen is None:
                # Cached target died (tab closed, Chrome restarted, …);
                # forget it before falling back so we don't keep paying
                # the lookup cost on every attach.
                profile.clear_target()

    if chosen is None:
        non_blank = [t for t in pages if t.get("url") and t.get("url") != "about:blank"]
        chosen = non_blank[0] if non_blank else pages[0]

    if profile is not None:
        target_id = chosen.get("id")
        if isinstance(target_id, str):
            profile.save_target(target_id)

    return str(chosen["webSocketDebuggerUrl"])


async def _list_page_targets(
    session: aiohttp.ClientSession, host: str, port: int
) -> list[dict[str, Any]]:
    url = f"http://{host}:{port}/json"
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
        targets = await resp.json(content_type=None)
    if not isinstance(targets, list):
        return []
    return [t for t in targets if isinstance(t, dict) and t.get("type") == "page"]


async def _create_blank_page_target(
    session: aiohttp.ClientSession, host: str, port: int
) -> dict[str, Any] | None:
    """Create a blank page target when Chrome has no page targets.

    Chromium documents ``/json/new`` as a PUT endpoint, while older builds and
    some Chromium derivatives also accept GET. Try PUT first and fall back to
    GET so an already-running debug server with zero tabs can recover without
    requiring users to restart Chrome.
    """
    url = f"http://{host}:{port}/json/new?about:blank"
    timeout = aiohttp.ClientTimeout(total=5)
    methods = []
    put = getattr(session, "put", None)
    if put is not None:
        methods.append(put)
    methods.append(session.get)
    for method in methods:
        try:
            async with method(url, timeout=timeout) as resp:
                if resp.status >= 400:
                    continue
                payload = await resp.json(content_type=None)
        except Exception:  # noqa: BLE001  # pylint: disable=broad-except
            continue
        if isinstance(payload, dict) and payload.get("type") == "page":
            return payload
    return None
