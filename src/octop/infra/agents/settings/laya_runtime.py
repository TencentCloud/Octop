"""Install and run Laya in an isolated environment under Octop's home.

The service is a normal ``laya-serve`` process, not a container. Progress is
kept on the runtime so a closed page can reconnect to the same install.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shlex
import shutil
import socket
import sys
import urllib.error
import urllib.request
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

from octop.i18n import tr
from octop.infra.utils.paths import PathLayout
from octop.infra.utils.posix_compat import killpg

LAYA_VERSION = "0.4.7"
LAYA_HOST = "127.0.0.1"
LAYA_PORT = 8000
LAYA_ENDPOINT = f"http://{LAYA_HOST}:{LAYA_PORT}/v1/systemone"
_HEALTH_URL = f"http://{LAYA_HOST}:{LAYA_PORT}/health"
_CPU_TORCH_INDEX = "https://download.pytorch.org/whl/cpu"
_MIN_FREE_BYTES = 4 * 1024**3
_NEED_GB = 4
_HEALTH_TIMEOUT = 600.0
_POLL_INTERVAL = 2.0
_JOB_TIMEOUT = 1800.0
_LOG_LIMIT = 400
_SECRET = re.compile(
    r"(?i)((?:api[_-]?key|token|secret|authorization)\s*[:=]\s*(?:bearer\s+)?)(\S+)"
)

CommandRunner = Callable[[list[str], dict[str, str], Callable[[str], None]], Awaitable[int]]
Probe = Callable[[], bool]
BytesProbe = Callable[[], int]
Starter = Callable[[], Awaitable[None]]


def redact(text: str) -> str:
    """Hide credentials before a line is stored or shown."""
    return _SECRET.sub(r"\1[redacted]", text)


def venv_python(root: Path) -> Path:
    folder = "Scripts" if os.name == "nt" else "bin"
    name = "python.exe" if os.name == "nt" else "python"
    return root / "venv" / folder / name


def serve_bin(root: Path) -> Path:
    folder = "Scripts" if os.name == "nt" else "bin"
    name = "laya-serve.exe" if os.name == "nt" else "laya-serve"
    return root / "venv" / folder / name


_COMPATIBLE_PYTHONS = ("3.12", "3.11", "3.13", "3.10")


def compatible_python(
    *,
    which: Callable[[str], str | None] = shutil.which,
    current_version: tuple[int, int] | None = None,
    current: Path | None = None,
) -> Path | None:
    """Pick a Python that still has a CPU torch wheel.

    Octop itself may run on a newer interpreter. Laya is installed into its
    own environment, so the interpreter does not have to be Octop's.
    """
    for version in _COMPATIBLE_PYTHONS:
        found = which(f"python{version}")
        if found:
            return Path(found)
    running = current_version or (sys.version_info[0], sys.version_info[1])
    if (3, 10) <= running <= (3, 13):
        return current or Path(sys.executable)
    return None


def format_install_command(base_python: Path, root: Path) -> str:
    """Shell form of the automatic install, shown before it runs."""
    lines = [shlex.join(argv) for argv in install_commands(base_python, venv_python(root))]
    serve = shlex.quote(str(serve_bin(root)))
    lines.append(
        "LAYA_HOST=127.0.0.1 LAYA_PORT=8000 LAYA_DEVICE=cpu "
        f"LAYA_MODELS=multilingual LAYA_PRELOAD=1 {serve}"
    )
    return "\n".join(lines)


def install_commands(base_python: Path, python: Path) -> list[list[str]]:
    """Create the environment, then install a CPU torch before Laya."""
    package = f"laya[serve]=={LAYA_VERSION}"
    return [
        [str(base_python), "-m", "venv", str(python.parent.parent)],
        [str(python), "-m", "pip", "install", "--upgrade", "pip"],
        [str(python), "-m", "pip", "install", "torch", "--index-url", _CPU_TORCH_INDEX],
        [str(python), "-m", "pip", "install", package],
    ]


def _sse(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _default_port_busy() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((LAYA_HOST, LAYA_PORT)) == 0


def _default_health() -> bool:
    try:
        with urllib.request.urlopen(_HEALTH_URL, timeout=1) as response:
            return int(response.status) == 200
    except (OSError, urllib.error.URLError, TimeoutError, ValueError):
        return False


def _default_free_bytes(root: Path) -> int:
    target = root if root.exists() else root.parent
    try:
        return int(shutil.disk_usage(target).free)
    except OSError:
        return _MIN_FREE_BYTES


def child_env(root: Path) -> dict[str, str]:
    """Environment for pip and laya-serve. Secrets are not forwarded."""
    allowed = {
        "PATH",
        "HOME",
        "USERPROFILE",
        "LANG",
        "LC_ALL",
        "SYSTEMROOT",
        "SSL_CERT_FILE",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
        "all_proxy",
    }
    env = {key: value for key, value in os.environ.items() if key in allowed}
    env["PATH"] = os.environ.get("PATH", "")
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["HF_HOME"] = str(root / "cache")
    env["LAYA_HOST"] = LAYA_HOST
    env["LAYA_PORT"] = str(LAYA_PORT)
    env["LAYA_DEVICE"] = "cpu"
    env["LAYA_MODELS"] = "multilingual"
    env["LAYA_PRELOAD"] = "1"
    env["LAYA_THREADS"] = str(min(4, os.cpu_count() or 1))
    return env


async def _stream_command(
    argv: list[str],
    env: dict[str, str],
    emit: Callable[[str], None],
) -> int:
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
    except OSError as exc:
        emit(str(exc))
        return 127
    assert proc.stdout is not None
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        emit(redact(line.decode("utf-8", errors="replace").rstrip()))
    return await proc.wait()


class LayaRuntime:
    """One managed Laya install for this Octop home."""

    def __init__(
        self,
        root: Path | None = None,
        *,
        runner: CommandRunner | None = None,
        health_check: Probe | None = None,
        port_busy: Probe | None = None,
        free_bytes: BytesProbe | None = None,
        starter: Starter | None = None,
        base_python: Path | None = None,
        health_timeout: float = _HEALTH_TIMEOUT,
        poll_interval: float = _POLL_INTERVAL,
    ) -> None:
        self.root = root or (PathLayout.from_env().root / "laya")
        self._runner = runner or _stream_command
        self._health_check = health_check or _default_health
        self._port_busy = port_busy or _default_port_busy
        self._free_bytes = free_bytes or (lambda: _default_free_bytes(self.root))
        self._starter = starter
        self._base_python = base_python if base_python is not None else compatible_python()
        self._health_timeout = health_timeout
        self._poll_interval = poll_interval
        self._phase = "idle"
        self._lines: list[str] = []
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._proc: asyncio.subprocess.Process | None = None

    @property
    def python_path(self) -> Path:
        return venv_python(self.root)

    @property
    def server_path(self) -> Path:
        return serve_bin(self.root)

    @property
    def installed(self) -> bool:
        return self.server_path.is_file()

    def command_text(self) -> str:
        if self._base_python is None:
            return ""
        return format_install_command(self._base_python, self.root)

    def snapshot(self, *, running: bool) -> dict[str, Any]:
        installed = self.installed
        if self._phase == "installing":
            phase = "installing"
        elif self._phase == "starting":
            phase = "starting"
        elif running:
            phase = "running"
        elif self._phase == "failed":
            phase = "failed"
        elif installed:
            phase = "stopped"
        else:
            phase = "missing"
        return {
            "installed": installed,
            "running": running,
            "managed": self._managed_pid() is not None,
            "phase": phase,
            "endpoint": LAYA_ENDPOINT,
            "port": LAYA_PORT,
            "command": self.command_text(),
            "logs": self._visible_logs(),
        }

    async def status(self) -> dict[str, Any]:
        running = await asyncio.to_thread(self._health_check)
        return self.snapshot(running=running)

    async def install_events(self, locale: str) -> AsyncIterator[str]:
        await self._ensure_task(locale)
        index = 0
        try:
            while True:
                while index < len(self._lines):
                    yield _sse({"log": self._lines[index]})
                    index += 1
                if self._phase != "installing":
                    ready = self._phase == "ready"
                    yield _sse(
                        {
                            "done": True,
                            "success": ready,
                            "endpoint": LAYA_ENDPOINT if ready else "",
                        }
                    )
                    return
                await asyncio.sleep(0.25)
        except asyncio.CancelledError:
            return

    async def start(self, locale: str = "en") -> dict[str, Any]:
        if self._phase == "installing":
            return await self.status()
        if not self.installed:
            self._fail(tr("laya.error_not_installed", locale))
            return await self.status()
        if await asyncio.to_thread(self._health_check):
            self._phase = "running"
            return await self.status()
        self._phase = "starting"
        self._say(tr("laya.started", locale))
        try:
            await self._spawn()
        except OSError as exc:
            self._fail(tr("laya.error_spawn", locale, command="laya-serve", error=exc))
            return await self.status()
        self._task = asyncio.create_task(self._watch_health(locale))
        return await self.status()

    async def stop(self, locale: str = "en") -> dict[str, Any]:
        await self._stop_process()
        self._phase = "stopped" if self.installed else "missing"
        self._say(tr("laya.stopped", locale))
        return await self.status()

    async def _ensure_task(self, locale: str) -> None:
        async with self._lock:
            if self._task is not None and not self._task.done() and self._phase == "installing":
                return
            self._lines = []
            self._phase = "installing"
            self._task = asyncio.create_task(self._job(locale))

    async def _job(self, locale: str) -> None:
        try:
            await asyncio.wait_for(self._install(locale), timeout=_JOB_TIMEOUT)
        except TimeoutError:
            self._fail(tr("laya.error_stalled", locale))
        except asyncio.CancelledError:
            self._phase = "failed"
            raise
        except Exception as exc:  # noqa: BLE001 — surface the failure in the install log
            self._fail(redact(str(exc)))

    async def _install(self, locale: str) -> None:
        self._say(tr("laya.install_start", locale))
        if await asyncio.to_thread(self._health_check):
            self._say(tr("laya.already_running", locale, port=LAYA_PORT))
            self._phase = "ready"
            return
        if self._base_python is None:
            self._fail(tr("laya.error_python", locale))
            return
        if await asyncio.to_thread(self._port_busy):
            self._fail(tr("laya.error_port", locale, port=LAYA_PORT))
            return
        free = await asyncio.to_thread(self._free_bytes)
        if free < _MIN_FREE_BYTES:
            self._fail(
                tr(
                    "laya.error_disk",
                    locale,
                    free_gb=round(free / 1024**3, 1),
                    need_gb=_NEED_GB,
                )
            )
            return
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "cache").mkdir(exist_ok=True)
        python = self.python_path
        self._say(tr("laya.install_python", locale, python=self._base_python))
        self._say(tr("laya.install_venv", locale, path=self.root / "venv"))
        commands = install_commands(self._base_python, python)
        skip_venv = python.is_file()
        if skip_venv:
            commands = commands[1:]
        notes = {
            1: tr("laya.install_torch", locale),
            2: tr("laya.install_package", locale, version=LAYA_VERSION),
        }
        env = child_env(self.root)
        for index, argv in enumerate(commands):
            note = notes.get(index if skip_venv else index - 1)
            if note:
                self._say(note)
            code = await self._runner(argv, env, self._say)
            if code != 0:
                self._fail(
                    tr(
                        "laya.error_command",
                        locale,
                        exit_code=code,
                        command=" ".join(argv),
                    )
                )
                return
        if not self.server_path.is_file():
            self._fail(tr("laya.error_missing_bin", locale))
            return
        self._say(tr("laya.install_server", locale, port=LAYA_PORT))
        try:
            await self._spawn()
        except OSError as exc:
            self._fail(tr("laya.error_spawn", locale, command="laya-serve", error=exc))
            return
        if not await self._wait_until_ready(locale):
            return
        self._say(tr("laya.install_ready", locale, endpoint=LAYA_ENDPOINT))
        self._phase = "ready"

    async def _wait_until_ready(self, locale: str) -> bool:
        waited = 0.0
        announced = 0
        while waited <= self._health_timeout:
            if await asyncio.to_thread(self._health_check):
                return True
            if self._proc is not None and self._proc.returncode is not None:
                self._fail(tr("laya.error_exited", locale))
                return False
            if int(waited) >= announced + 15:
                announced = int(waited)
                self._say(tr("laya.install_wait", locale, seconds=announced))
            await asyncio.sleep(self._poll_interval)
            waited += self._poll_interval
        self._fail(tr("laya.error_health", locale))
        return False

    async def _watch_health(self, locale: str) -> None:
        if await self._wait_until_ready(locale):
            self._phase = "running"

    async def _spawn(self) -> None:
        if self._starter is not None:
            await self._starter()
            return
        log_path = self.root / "serve.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handle = log_path.open("ab", buffering=0)
        env = child_env(self.root)
        bin_dir = str(self.server_path.parent)
        env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
        try:
            if os.name == "nt":
                self._proc = await asyncio.create_subprocess_exec(
                    str(self.server_path),
                    stdout=handle,
                    stderr=asyncio.subprocess.STDOUT,
                    env=env,
                    cwd=str(self.root),
                )
            else:
                self._proc = await asyncio.create_subprocess_exec(
                    str(self.server_path),
                    stdout=handle,
                    stderr=asyncio.subprocess.STDOUT,
                    env=env,
                    cwd=str(self.root),
                    start_new_session=True,
                )
        finally:
            handle.close()
        (self.root / "laya.pid").write_text(str(self._proc.pid), encoding="utf-8")

    async def _stop_process(self) -> None:
        proc = self._proc
        pid = proc.pid if proc is not None and proc.returncode is None else self._managed_pid()
        if pid is None:
            return
        with contextlib.suppress(OSError):
            if os.name == "nt":
                os.kill(pid, 15)
            else:
                killpg(pid, 15)
        if proc is not None:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(proc.wait(), timeout=5)
        self._proc = None
        pid_path = self.root / "laya.pid"
        if pid_path.is_file():
            pid_path.unlink()

    def _managed_pid(self) -> int | None:
        if self._proc is not None and self._proc.returncode is None:
            return self._proc.pid
        pid_path = self.root / "laya.pid"
        if not pid_path.is_file():
            return None
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except ValueError:
            return None
        try:
            os.kill(pid, 0)
        except OSError:
            return None
        return pid

    def _say(self, text: str) -> None:
        line = redact(text).strip()
        if not line:
            return
        self._lines.append(line)
        if len(self._lines) > _LOG_LIMIT:
            self._lines = self._lines[-_LOG_LIMIT:]
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            with (self.root / "install.log").open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            return

    def _fail(self, text: str) -> None:
        self._say(text)
        self._phase = "failed"

    def _visible_logs(self) -> list[str]:
        if self._lines:
            return list(self._lines[-_LOG_LIMIT:])
        path = self.root / "install.log"
        if not path.is_file():
            return []
        try:
            rows = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
        return [redact(row) for row in rows[-_LOG_LIMIT:]]


_RUNTIME: LayaRuntime | None = None


def get_laya_runtime() -> LayaRuntime:
    global _RUNTIME
    if _RUNTIME is None:
        _RUNTIME = LayaRuntime()
    return _RUNTIME
