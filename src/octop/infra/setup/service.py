"""System service helpers for systemd (Linux) and launchd (macOS)."""

from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from octop.config import load_config
from octop.infra.utils import posix_compat as pwd
from octop.infra.utils.paths import PathLayout
from octop.infra.utils.posix_compat import chown, geteuid, getuid, is_root

logger = logging.getLogger(__name__)

ServiceMode = Literal["systemd", "launchd"]
ServiceScope = Literal["user", "system"]

SERVICE_NAME = "octop"
SYSTEMD_UNIT = f"{SERVICE_NAME}.service"
LAUNCHD_LABEL = SERVICE_NAME

# Give freshly-started services a moment to bind the port before health checks
# begin.  `octop run` typically takes several seconds to initialise DB, load
# agents, and start accepting HTTP requests.
_STARTUP_GRACE_SECONDS = 5.0

# Polling budget for waiting on stop/restart.  30 * 1s = 30s total.
_STOP_POLL_ATTEMPTS = 30
_STOP_POLL_DELAY_SECONDS = 1.0

# Default retry budget for HTTP health probes.  With a 5s grace the total
# worst-case wait is 5 + 10*1.5 = 20s.
DEFAULT_HEALTH_ATTEMPTS = 10
DEFAULT_HEALTH_DELAY_SECONDS = 1.5

# When the port is bound but the server is not yet responding (e.g.
# "Server disconnected without sending a response."), retry sooner because
# the app is already initializing and likely to be ready soon.
_EARLY_RETRY_DELAY_SECONDS = 0.5

# Env var names used to override defaults.
_ENV_SCOPE = "OCTOP_SERVICE_SCOPE"


@dataclass(frozen=True)
class ServiceRuntime:
    mode: ServiceMode
    host: str
    port: int
    home: Path
    octop_bin: Path
    run_as_user: str
    scope: ServiceScope = "system"


@dataclass(frozen=True)
class ServiceStatus:
    mode: ServiceMode | None
    installed: bool
    active: bool
    enabled: bool | None
    detail: str
    health_ok: bool | None = None
    health_detail: str | None = None


def detect_service_mode() -> ServiceMode | None:
    """Return the service mode for the current process (from OCTOP_SERVICE_MODE)."""
    raw = os.environ.get("OCTOP_SERVICE_MODE", "").strip().lower()
    if raw in {"systemd", "launchd"}:
        return raw  # type: ignore[return-value]
    return None


def detect_platform_mode() -> ServiceMode | None:
    system = platform.system()
    if system == "Linux":
        return "systemd"
    if system == "Darwin":
        return "launchd"
    return None


def _auto_service_scope() -> ServiceScope:
    """Infer install scope based on the effective uid.

    Any process running as root (uid 0) installs a system unit under
    ``/etc/systemd/system``.  Non-root processes install a user unit under
    ``~/.config/systemd/user``.  ``SUDO_USER`` is intentionally ignored here:
    when root runs ``octop service start`` the expected outcome is always a
    system-level service, regardless of how root was obtained.
    """
    if is_root():
        return "system"
    return "user"


def resolve_service_scope(*, default: ServiceScope | None = None) -> ServiceScope:
    """Decide between ``user`` and ``system`` scope.

    Resolution order:

    1. ``OCTOP_SERVICE_SCOPE`` env var (``user`` / ``system`` / ``auto``).
    2. ``default`` argument, if provided.
    3. Auto: root → ``system``, otherwise → ``user``.

    On Linux ``user`` corresponds to ``systemctl --user`` (no sudo) and
    ``system`` to a unit under ``/etc/systemd/system`` (sudo required).
    On macOS ``user`` writes the plist to ``~/Library/LaunchAgents`` and
    loads it into the ``gui/$UID`` domain (no sudo); ``system`` writes to
    ``/Library/LaunchDaemons`` and loads into ``system`` (sudo required).
    """
    raw = os.environ.get(_ENV_SCOPE, "").strip().lower()
    if raw in {"user", "system"}:
        return raw  # type: ignore[return-value]
    if raw == "auto":
        return _auto_service_scope()
    if default is not None:
        return default
    return _auto_service_scope()


def launchd_domain(scope: ServiceScope) -> str:
    """Return the launchd service-target for the given scope.

    This is the form accepted by `launchctl kickstart -k` / `bootout` /
    `print` — e.g. ``gui/$UID/octop`` for user scope.  For the `bootstrap`
    domain-target form (no service id), use :func:`launchd_bootstrap_target`.
    """
    if scope == "user":
        return f"gui/{getuid()}/{LAUNCHD_LABEL}"
    return f"system/{LAUNCHD_LABEL}"


def launchd_bootstrap_target(scope: ServiceScope) -> str:
    """Return the launchd domain-target for `launchctl bootstrap`.

    Unlike :func:`launchd_domain` this is the *target* (``gui/$UID``,
    ``system``), not a service-target.  Bare ``user`` / ``system`` is rejected
    by launchd on modern macOS — you must qualify user with a uid.
    """
    if scope == "user":
        return f"gui/{getuid()}"
    return "system"


def resolve_octop_executable(home: Path | None = None) -> Path:
    root = home or PathLayout.from_env().root
    for candidate in (
        root / "bin" / "octop",
        root / "venv" / "bin" / "octop",
        root / "venv" / "Scripts" / "octop.exe",
    ):
        if candidate.is_file():
            return candidate

    # Dev / conda / uv-tool installs: use the octop that invoked this command.
    for candidate in (
        Path(sys.executable).parent / "octop",
        Path(sys.executable).parent / "octop.exe",
    ):
        if candidate.is_file():
            return candidate

    found = shutil.which("octop")
    if found:
        return Path(found)

    raise FileNotFoundError(
        f"octop executable not found under {root} or on PATH; "
        "run `scripts/install.sh` or ensure `octop` is installed"
    )


def resolve_run_as_user() -> str:
    """Return the OS account the installed service should run as.

    Root always runs services as root (system scope).  Non-root users run
    services as themselves (user scope).  ``SUDO_USER`` is ignored: when the
    process is root, the service should run as root regardless of how the
    session was obtained.
    """
    if is_root():
        return "root"
    for key in ("USER", "LOGNAME"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return "root"


def _account_home(user: str) -> Path:
    """Home directory for ``user`` from passwd (not the installer's euid)."""
    try:
        return Path(pwd.getpwnam(user).pw_dir)
    except KeyError:
        if user == os.environ.get("USER", ""):
            return Path.home()
        return Path(f"/home/{user}")


def resolve_service_home(*, run_as_user: str | None = None) -> Path:
    """Resolve ``OCTOP_HOME`` for the service owner, not the installer's euid.

    ``Path.home()`` follows the effective uid, so a ``sudo`` install as root
    would otherwise point at ``/root/.octop`` while ``User=`` names the
    invoking user — use that user's passwd home instead.
    """
    raw = os.environ.get("OCTOP_HOME", "").strip()
    if raw:
        return Path(raw).expanduser()
    user = run_as_user or resolve_run_as_user()
    return _account_home(user) / ".octop"


def persist_bind_options(home: Path, *, host: str | None = None, port: int | None = None) -> None:
    """Write bind host/port into ``config.json`` before (re)installing the unit."""
    if host is None and port is None:
        return
    config_path = home / "config.json"
    data: dict[str, object] = {}
    if config_path.is_file():
        with suppress(OSError, json.JSONDecodeError):
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
    if host is not None:
        data["bind_host"] = host
    if port is not None:
        data["port"] = port
    home.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def resolve_bind_options(home: Path | None = None) -> tuple[str, int]:
    root = home or PathLayout.from_env().root
    config_path = root / "config.json"
    if config_path.is_file():
        config = load_config(config_path)
        return config.bind_host, config.port
    return "127.0.0.1", 8088


def build_runtime(
    *,
    home: Path | None = None,
    host: str | None = None,
    port: int | None = None,
    mode: ServiceMode | None = None,
    scope: ServiceScope | None = None,
) -> ServiceRuntime:
    resolved_mode = mode or detect_platform_mode()
    if resolved_mode is None:
        raise RuntimeError("system services are only supported on Linux and macOS")
    run_as_user = resolve_run_as_user()
    root = home or resolve_service_home(run_as_user=run_as_user)
    bind_host, bind_port = resolve_bind_options(root)
    return ServiceRuntime(
        mode=resolved_mode,
        host=host or bind_host,
        port=port or bind_port,
        home=root,
        octop_bin=resolve_octop_executable(root),
        run_as_user=run_as_user,
        scope=scope or resolve_service_scope(),
    )


def _sudo_as_user_prefix(run_as_user: str) -> list[str]:
    if not is_root() or run_as_user == "root":
        return []
    return ["sudo", "-u", run_as_user]


def _systemd_user_cmd_prefix(run_as_user: str) -> list[str]:
    """Prefix for ``systemctl --user`` when the installer is root but the owner is not."""
    prefix = _sudo_as_user_prefix(run_as_user)
    if not prefix:
        return []
    uid = pwd.getpwnam(run_as_user).pw_uid
    # ``VAR=val`` only works in a shell; subprocess needs ``env VAR=val``.
    return [*prefix, "env", f"XDG_RUNTIME_DIR=/run/user/{uid}"]


def _systemctl(scope: ServiceScope, *args: str, run_as_user: str | None = None) -> list[str]:
    user = run_as_user or resolve_run_as_user()
    if scope == "user":
        return [*_systemd_user_cmd_prefix(user), "systemctl", "--user", *args]
    return ["systemctl", *args]


def _systemd_run(
    runtime: ServiceRuntime,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    use_sudo = runtime.scope == "system" and not is_root()
    return _run_cmd(
        _systemctl(runtime.scope, *args, run_as_user=runtime.run_as_user),
        use_sudo=use_sudo,
    )


def _systemd_enable_linger(runtime: ServiceRuntime) -> None:
    """Keep user services running after logout (best-effort)."""
    if runtime.scope != "user":
        return
    import getpass

    user = runtime.run_as_user
    cmd = [*_sudo_as_user_prefix(user), "loginctl", "enable-linger", user]
    # NOCA:DangerousSubprocessUseAudit(argv list with shell=False; loginctl service helper)
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        logger.info(
            "could not enable linger automatically; run: loginctl enable-linger %s",
            user if is_root() and user != getpass.getuser() else getpass.getuser(),
        )


def unit_path(
    mode: ServiceMode,
    scope: ServiceScope | None = None,
    *,
    run_as_user: str | None = None,
) -> Path:
    """Return the on-disk path where the unit file should live for ``mode``/``scope``.

    ``scope`` defaults to the inferred value via :func:`resolve_service_scope`.
    User-level paths are resolved from the service owner's passwd home, not the
    installer's ``Path.home()`` (so ``sudo`` does not point at ``/root``).
    """
    owner_home = _account_home(run_as_user or resolve_run_as_user())
    if mode == "systemd":
        if scope is None:
            scope = resolve_service_scope()
        if scope == "user":
            return owner_home / ".config" / "systemd" / "user" / SYSTEMD_UNIT
        return Path("/etc/systemd/system") / SYSTEMD_UNIT
    if scope is None:
        scope = resolve_service_scope()
    if scope == "user":
        return owner_home / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"
    return Path("/Library/LaunchDaemons") / f"{LAUNCHD_LABEL}.plist"


def is_service_installed(
    mode: ServiceMode,
    scope: ServiceScope | None = None,
    *,
    run_as_user: str | None = None,
) -> bool:
    return unit_path(mode, scope=scope, run_as_user=run_as_user).is_file()


def render_systemd_unit(runtime: ServiceRuntime, *, user_unit: bool | None = None) -> str:
    if user_unit is None:
        user_unit = runtime.scope == "user"
    account_home = _account_home(runtime.run_as_user)
    # LightClaw-style: HOME + service mode + config-driven ``run``.  Octop also
    # sets ``OCTOP_HOME`` explicitly.  No ``WorkingDirectory`` — avoids CHDIR
    # failures when ``User=`` and data paths disagree.
    if user_unit or runtime.run_as_user == "root":
        user_line = ""
    else:
        user_line = f"User={runtime.run_as_user}\n"
    wanted_by = "default.target" if user_unit else "multi-user.target"
    env_lines = (
        f'Environment="HOME={account_home}"\n'
        f"Environment=OCTOP_HOME={runtime.home}\n"
        "Environment=OCTOP_SERVICE_MODE=systemd\n"
    )
    if user_unit:
        env_lines += "Environment=OCTOP_SYSTEMD_USER=1\n"
    return (
        "[Unit]\n"
        "Description=Octop AI Server\n"
        "After=network.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"{user_line}"
        f"{env_lines}"
        f"ExecStart={runtime.octop_bin} run\n"
        "Restart=on-failure\n"
        "RestartSec=5\n"
        "TimeoutStopSec=30\n"
        "\n"
        "[Install]\n"
        f"WantedBy={wanted_by}\n"
    )


def render_launchd_plist(runtime: ServiceRuntime) -> str:
    """Render the launchd plist for ``runtime``.

    ``UserName`` is only valid for system-domain (``/Library/LaunchDaemons``)
    plists; launchd rejects it for user-domain agents and the agent runs as
    the logged-in user automatically.
    """
    log_path = runtime.home / "logs" / "octop.log"
    account_home = _account_home(runtime.run_as_user)
    user_block = (
        f"  <key>UserName</key>\n  <string>{runtime.run_as_user}</string>\n"
        if runtime.scope == "system"
        else ""
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        f"  <key>Label</key>\n"
        f"  <string>{LAUNCHD_LABEL}</string>\n"
        f"{user_block}"
        "  <key>ProgramArguments</key>\n"
        "  <array>\n"
        f"    <string>{runtime.octop_bin}</string>\n"
        "    <string>run</string>\n"
        "  </array>\n"
        "  <key>EnvironmentVariables</key>\n"
        "  <dict>\n"
        f"    <key>HOME</key>\n"
        f"    <string>{account_home}</string>\n"
        f"    <key>OCTOP_HOME</key>\n"
        f"    <string>{runtime.home}</string>\n"
        "    <key>OCTOP_SERVICE_MODE</key>\n"
        "    <string>launchd</string>\n"
        "  </dict>\n"
        f"  <key>WorkingDirectory</key>\n"
        f"  <string>{runtime.home}</string>\n"
        "  <key>RunAtLoad</key>\n"
        "  <true/>\n"
        "  <key>KeepAlive</key>\n"
        "  <true/>\n"
        f"  <key>StandardOutPath</key>\n"
        f"  <string>{log_path}</string>\n"
        f"  <key>StandardErrorPath</key>\n"
        f"  <string>{log_path}</string>\n"
        "</dict>\n"
        "</plist>\n"
    )


def _needs_sudo(path: Path) -> bool:
    return not path.parent.exists() or not os.access(path.parent, os.W_OK)


def _run_cmd(cmd: list[str], *, use_sudo: bool) -> subprocess.CompletedProcess[str]:
    full = ["sudo", *cmd] if use_sudo and geteuid() != 0 else cmd
    # NOCA:DangerousSubprocessUseAudit(argv list with shell=False; systemctl/launchctl service management)
    return subprocess.run(full, capture_output=True, text=True, check=False)


def _cmd_ok(proc: subprocess.CompletedProcess[str], fallback: str) -> None:
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or fallback).strip()
        raise RuntimeError(detail)


def _write_unit(runtime: ServiceRuntime) -> None:
    destination = unit_path(runtime.mode, scope=runtime.scope, run_as_user=runtime.run_as_user)
    content = (
        render_systemd_unit(runtime) if runtime.mode == "systemd" else render_launchd_plist(runtime)
    )
    use_sudo = _needs_sudo(destination)
    if use_sudo and geteuid() != 0:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tmp:
            tmp.write(content)
            tmp.flush()
            tmp_path = tmp.name
        try:
            mkdir_proc = _run_cmd(["mkdir", "-p", str(destination.parent)], use_sudo=True)
            _cmd_ok(mkdir_proc, f"failed to create {destination.parent}")
            proc = _run_cmd(["cp", tmp_path, str(destination)], use_sudo=True)
            _cmd_ok(proc, "failed to write unit file")
            _run_cmd(["chmod", "644", str(destination)], use_sudo=True)
            if runtime.run_as_user != "root":
                _run_cmd(
                    ["chown", f"{runtime.run_as_user}:{runtime.run_as_user}", str(destination)],
                    use_sudo=True,
                )
        finally:
            os.unlink(tmp_path)
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    destination.chmod(0o644)
    if is_root() and runtime.run_as_user != "root":
        chown(destination, pwd.getpwnam(runtime.run_as_user).pw_uid, -1)


def _launchctl_run(scope: ServiceScope, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a launchctl command for the given scope.

    `user` scope runs unsudo'd (gui/$UID is writable by the current user);
    `system` scope falls back to sudo when not running as root.
    """
    use_sudo = scope == "system" and geteuid() != 0
    return _run_cmd(["launchctl", *args], use_sudo=use_sudo)


def _launchctl_run_tolerant(
    scope: ServiceScope,
    *args: str,
    ignore_substrings: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    """Like :func:`_launchctl_run` but tolerates known non-fatal error text.

    `launchctl bootstrap` exits non-zero when the service is already loaded;
    `bootout` exits non-zero when the service was never loaded.  These are
    not errors from our perspective — match the substrings case-insensitively
    and only raise for anything else.
    """
    proc = _launchctl_run(scope, *args)
    if proc.returncode == 0:
        return proc
    combined = (proc.stderr or proc.stdout or "").lower()
    if any(token in combined for token in ignore_substrings):
        return proc
    _cmd_ok(proc, f"launchctl {' '.join(args)} failed")
    return proc  # unreachable, satisfies type checkers


def _launchd_bootstrap(runtime: ServiceRuntime) -> None:
    _launchctl_run_tolerant(
        runtime.scope,
        "bootstrap",
        launchd_bootstrap_target(runtime.scope),
        str(unit_path(runtime.mode, scope=runtime.scope, run_as_user=runtime.run_as_user)),
        ignore_substrings=("already", "loaded"),
    )


def _launchd_reload(runtime: ServiceRuntime) -> None:
    # macOS launchd reports the not-loaded case as either "Could not find
    # specified service" or "no such service" depending on the version; cover
    # both phrasings.
    _launchctl_run_tolerant(
        runtime.scope,
        "bootout",
        launchd_domain(runtime.scope),
        ignore_substrings=("no such", "could not find"),
    )
    _launchd_bootstrap(runtime)


def install_service(
    runtime: ServiceRuntime,
    *,
    force: bool = False,
) -> None:
    was_installed = is_service_installed(
        runtime.mode, scope=runtime.scope, run_as_user=runtime.run_as_user
    )
    if was_installed and not force:
        return
    _write_unit(runtime)
    if runtime.mode == "systemd":
        proc = _systemd_run(runtime, "daemon-reload")
        _cmd_ok(proc, "daemon-reload failed")
        proc = _systemd_run(runtime, "enable", SERVICE_NAME)
        _cmd_ok(proc, "systemctl enable failed")
        _systemd_enable_linger(runtime)
        return

    if was_installed and force:
        _launchd_reload(runtime)
    else:
        _launchd_bootstrap(runtime)


def _wait_for_stop(runtime: ServiceRuntime) -> None:
    """Poll ``collect_service_status`` until the service reports ``active=False``.

    Times out after ``_STOP_POLL_ATTEMPTS`` checks (default 30s).  Used after
    ``stop`` / ``bootout`` so that subsequent commands (e.g. ``bootstrap`` in a
    restart) don't race with the shutting-down process.
    """
    for _ in range(_STOP_POLL_ATTEMPTS):
        status = collect_service_status(runtime, check_health=False)
        if not status.active:
            return
        time.sleep(_STOP_POLL_DELAY_SECONDS)
    logger.warning("service did not stop within %ds — proceeding anyway", _STOP_POLL_ATTEMPTS)


def _wait_for_startup() -> None:
    """Give the service a moment to bind the port before health checks begin.

    Prevents the false-negative "active=True, health=unreachable" report that
    occurs when the server is still initialising DB and agents.
    """
    time.sleep(_STARTUP_GRACE_SECONDS)


def start_service(runtime: ServiceRuntime) -> None:
    if runtime.mode == "systemd":
        proc = _systemd_run(runtime, "start", SERVICE_NAME)
    else:
        proc = _launchctl_run(runtime.scope, "kickstart", "-k", launchd_domain(runtime.scope))
    _cmd_ok(proc, "start failed")
    _wait_for_startup()


def stop_service(runtime: ServiceRuntime) -> None:
    if not is_service_installed(runtime.mode, scope=runtime.scope, run_as_user=runtime.run_as_user):
        return
    if runtime.mode == "systemd":
        proc = _systemd_run(runtime, "stop", SERVICE_NAME)
        _cmd_ok(proc, "stop failed")
        _wait_for_stop(runtime)
    else:
        proc = _launchctl_run(runtime.scope, "bootout", launchd_domain(runtime.scope))
        _cmd_ok(proc, "stop failed")
        _wait_for_stop(runtime)


def restart_service(runtime: ServiceRuntime) -> None:
    if not is_service_installed(runtime.mode, scope=runtime.scope, run_as_user=runtime.run_as_user):
        raise RuntimeError(
            "octop system service is not installed "
            f"(expected {unit_path(runtime.mode, scope=runtime.scope, run_as_user=runtime.run_as_user)})"
        )
    if runtime.mode == "systemd":
        proc = _systemd_run(runtime, "restart", SERVICE_NAME)
    else:
        # launchd: bootout → wait for stop → bootstrap (kickstart -k is async
        # and can leave the old process's port bound when the new one starts).
        proc = _launchctl_run(runtime.scope, "bootout", launchd_domain(runtime.scope))
        _cmd_ok(proc, "restart bootout failed")
        _wait_for_stop(runtime)
        _launchd_bootstrap(runtime)
        _wait_for_startup()
        return
    _cmd_ok(proc, "restart failed")
    _wait_for_startup()


def _systemd_status(runtime: ServiceRuntime) -> tuple[bool, bool | None, str]:
    active_proc = _systemd_run(runtime, "is-active", SERVICE_NAME)
    active = active_proc.stdout.strip() == "active"
    enabled_proc = _systemd_run(runtime, "is-enabled", SERVICE_NAME)
    enabled_raw = enabled_proc.stdout.strip()
    enabled = enabled_raw == "enabled" if enabled_proc.returncode == 0 else None
    detail_proc = _systemd_run(runtime, "status", SERVICE_NAME, "--no-pager")
    detail = (detail_proc.stdout or detail_proc.stderr or "").strip()
    return active, enabled, detail


def _launchd_status(scope: ServiceScope) -> tuple[bool, bool | None, str]:
    proc = _launchctl_run(scope, "print", launchd_domain(scope))
    if proc.returncode != 0:
        return (
            False,
            is_service_installed("launchd", scope=scope),
            (proc.stderr or proc.stdout or "").strip(),
        )
    detail = proc.stdout.strip()
    active = "state = running" in detail.lower()
    return active, is_service_installed("launchd", scope=scope), detail


def probe_health(host: str, port: int) -> tuple[bool, str]:
    import httpx

    url = f"http://{host}:{port}/api/health"
    try:
        response = httpx.get(url, timeout=3)
        response.raise_for_status()
        return True, str(response.json())
    except Exception as exc:  # noqa: BLE001 - health probe should swallow any failure
        return False, str(exc)


def probe_health_with_retry(
    host: str,
    port: int,
    *,
    attempts: int = DEFAULT_HEALTH_ATTEMPTS,
    delay_seconds: float = DEFAULT_HEALTH_DELAY_SECONDS,
) -> tuple[bool, str]:
    last_detail = ""
    for attempt in range(attempts):
        ok, detail = probe_health(host, port)
        if ok:
            return True, detail
        last_detail = detail
        if attempt < attempts - 1:
            # Port bound but server not yet responding → retry sooner.
            if "disconnected without sending a response" in detail:
                time.sleep(_EARLY_RETRY_DELAY_SECONDS)
            else:
                time.sleep(delay_seconds)
    return False, last_detail


def collect_service_status(
    runtime: ServiceRuntime | None = None,
    *,
    check_health: bool = True,
    health_retries: int = 1,
    health_delay_seconds: float = DEFAULT_HEALTH_DELAY_SECONDS,
) -> ServiceStatus:
    mode = runtime.mode if runtime else detect_platform_mode()
    if mode is None:
        return ServiceStatus(
            mode=None,
            installed=False,
            active=False,
            enabled=None,
            detail="system services are only supported on Linux and macOS",
        )

    scope = runtime.scope if runtime is not None else resolve_service_scope()
    run_as = runtime.run_as_user if runtime is not None else None
    installed = is_service_installed(mode, scope=scope, run_as_user=run_as)
    if mode == "systemd":
        if runtime is None:
            active, enabled, detail = False, None, ""
        else:
            active, enabled, detail = _systemd_status(runtime)
    else:
        active, enabled, detail = _launchd_status(scope)

    health_ok: bool | None = None
    health_detail: str | None = None
    if check_health and runtime is not None:
        if health_retries > 1:
            health_ok, health_detail = probe_health_with_retry(
                runtime.host,
                runtime.port,
                attempts=health_retries,
                delay_seconds=health_delay_seconds,
            )
        else:
            health_ok, health_detail = probe_health(runtime.host, runtime.port)

    return ServiceStatus(
        mode=mode,
        installed=installed,
        active=active,
        enabled=enabled,
        detail=detail,
        health_ok=health_ok,
        health_detail=health_detail,
    )
