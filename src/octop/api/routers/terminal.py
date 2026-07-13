"""Terminal WebSocket — interactive PTY sessions per agent (P1.4).

  WS /api/agents/{agent_id}/terminal/ws?token=<JWT>&session_id=&cols=&rows=

The shell is spawned with the agent's ``workspace_dir`` as cwd so the
session lands the user where their files are. Authentication uses a
``?token=`` query string because browsers can't set ``Authorization``
on a WebSocket upgrade — the token mirrors the JWT issued at login.

Session persistence (opt-in)
----------------------------
Pass ``session_id`` to opt into a persistent session: the PTY + shell is
kept alive in a process-wide registry keyed by ``(agent_id, session_id)``
and survives a WebSocket disconnect for a grace period
(``_DETACH_GRACE_SECONDS``). Re-connecting with the same ``session_id``
re-attaches to the *same* shell and replays a bounded scrollback buffer
so the terminal history is restored (refresh / reconnect safe).

Omitting ``session_id`` keeps the original, backward-compatible behaviour:
an ephemeral shell that is destroyed as soon as the WebSocket closes.

Wire protocol (JSON over text frames)
-------------------------------------
Client → Server::

  {"type": "input",  "data": "ls\\n"}
  {"type": "resize", "cols": 100, "rows": 30}
  {"type": "close"}                                            # destroy now (skip grace)

Server → Client::

  {"type": "session", "session_id": "...", "agent_id": "..."}   # persistent only
  {"type": "history", "data": "<scrollback replay on re-attach>"} # persistent only
  {"type": "output",  "data": "<terminal bytes>"}
  {"type": "exit",    "code": 0}
  {"type": "error",   "message": "..."}

Limits
------
* Hard cap of ``_MAX_SESSIONS`` concurrent live shells process-wide
  (``_sessions`` registry). Excess *new* requests get a structured error
  + close code 4029 before the PTY is spawned. Re-attaching to an
  existing session does not consume a new slot.
* Each session is its own subprocess group (``os.setsid``) so SIGINT
  at close time only kills that group.
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
import json
import logging
import os
import platform
import shutil
import signal
import socket
import subprocess
import tempfile
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from octop.api.deps import current_user, get_server, resolve_user_from_token
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils import posix_compat

logger = logging.getLogger(__name__)

router = APIRouter()

# Maximum number of concurrent live shells (PTY processes), process-wide.
# Re-attaching to an existing persistent session does not count against this.
_MAX_SESSIONS = 10

# Per-session scrollback replay buffer (raw bytes). Replayed to the client on
# re-attach so terminal history survives a refresh / reconnect.
_MAX_SCROLLBACK_BYTES = 512 * 1024

# How long a detached persistent shell is kept alive waiting for a reconnect
# before it is reaped. Long enough to survive a refresh or a brief network drop.
_DETACH_GRACE_SECONDS = 300.0

_TERMINAL_UNSUPPORTED_REASON = (
    "Interactive web terminal is not supported on Windows. "
    "Use Linux or macOS, or run commands via the agent chat interface."
)


def terminal_supported() -> tuple[bool, str]:
    """Return ``(supported, reason_if_unsupported)`` for the PTY WebSocket terminal."""
    if os.name != "posix":
        return False, _TERMINAL_UNSUPPORTED_REASON
    try:
        import fcntl  # noqa: F401
        import pty  # noqa: F401
        import termios  # noqa: F401
    except ImportError:
        return False, "PTY terminal dependencies are not available on this platform."
    return True, ""


def _set_winsize(fd: int, cols: int, rows: int) -> None:
    """ioctl TIOCSWINSZ on the master fd. Errors are non-fatal."""
    try:
        posix_compat.set_winsize(fd, cols, rows)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("failed to set winsize: %s", exc)


def _detect_shell() -> str:
    """Resolve the shell for the current platform."""
    if os.name == "nt":
        comspec = os.environ.get("COMSPEC", "").strip()
        if comspec and os.path.exists(comspec):
            return comspec
        powershell = (
            os.environ.get("SYSTEMROOT", r"C:\Windows")
            + r"\System32\WindowsPowerShell\v1.0\powershell.exe"
        )
        if os.path.exists(powershell):
            return powershell
        return "cmd.exe"

    def _usable(path: str) -> bool:
        name = os.path.basename(path).lower()
        if name in {"nologin", "false", "true", "sync"}:
            return False
        return bool(path) and os.path.exists(path)

    shell = os.environ.get("SHELL", "").strip()
    if _usable(shell):
        return shell
    try:
        entry = posix_compat.getpwuid(posix_compat.getuid())
        shell = str(entry.pw_shell)
        if _usable(shell):
            return shell
    except Exception:  # pragma: no cover - non-posix
        pass
    for candidate in ("/bin/bash", "/bin/sh"):
        if os.path.exists(candidate):
            return candidate
    return "/bin/bash"


_ZSH_WEB_TERMINAL_RC = """\
# Octop web terminal — reduce stray blank / spacer lines in browser PTYs.
export PROMPT_EOL_MARK=
if [[ -f "${HOME}/.zshrc" ]]; then
  source "${HOME}/.zshrc"
fi
export PROMPT_EOL_MARK=
unsetopt prompt_sp 2>/dev/null
unsetopt prompt_cr 2>/dev/null
octop_web_terminal_precmd() {
  export PROMPT_EOL_MARK=
  unsetopt prompt_sp 2>/dev/null
}
typeset -ga precmd_functions
precmd_functions=("${precmd_functions[@]}" octop_web_terminal_precmd)
"""


def _zsh_web_zdotdir() -> str:
    """Return a temp ZDOTDIR whose .zshrc sources the user config then re-applies fixes."""
    d = tempfile.mkdtemp(prefix="octop-zdotdir-")
    with open(os.path.join(d, ".zshrc"), "w", encoding="utf-8") as fh:
        fh.write(_ZSH_WEB_TERMINAL_RC)
    return d


def _shell_env(*, shell: str) -> dict[str, str]:
    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    env.setdefault("LANG", "en_US.UTF-8")
    # Suppress zsh's PROMPT_EOL_MARK (the trailing "%" shown when output
    # does not end with a newline) — it appears as a stray "%" line in the
    # web terminal and is confusing to users.
    env["PROMPT_EOL_MARK"] = ""
    if "zsh" in shell:
        env["OCTOP_WEB_TERMINAL"] = "1"
    return env


class _PtySession:
    """A pseudo-terminal session that can outlive a single WS connection.

    The PTY + shell is owned by the session; attached WebSocket connections
    are mere subscribers fed via per-connection queues. Output keeps being
    captured into ``scrollback`` even while no client is attached, so a
    reconnect can replay the history.
    """

    def __init__(
        self,
        sid: str,
        agent_id: str,
        user_id: int,
        proc: subprocess.Popen[bytes],
        master_fd: int,
        cols: int,
        rows: int,
        persistent: bool,
        zdotdir: str | None = None,
    ) -> None:
        self.sid = sid
        self.agent_id = agent_id
        self.user_id = user_id
        self.persistent = persistent
        self.proc = proc
        self.master_fd = master_fd
        self.cols = cols
        self.rows = rows
        self.zdotdir = zdotdir
        # Bounded scrollback ring buffer (raw bytes), replayed on attach.
        self.scrollback: bytearray = bytearray()
        # Output fan-out queues, one per currently attached connection.
        self.subscribers: set[asyncio.Queue[dict[str, object]]] = set()
        self.pump_task: asyncio.Task[None] | None = None
        # Grace-period cleanup handle, armed when the last subscriber detaches.
        self.detach_handle: asyncio.TimerHandle | None = None
        # Reference to the deferred reap task (keeps it from being GC'd).
        self.reap_task: asyncio.Task[None] | None = None
        self.closed = False

    def append_scrollback(self, data: bytes) -> None:
        """Append output to the bounded scrollback buffer."""
        self.scrollback.extend(data)
        excess = len(self.scrollback) - _MAX_SCROLLBACK_BYTES
        if excess > 0:
            del self.scrollback[:excess]


# Process-wide registry of live terminal sessions, keyed by (agent_id, sid).
# The agent_id is part of the key so sessions can never leak across agents.
_sessions: dict[tuple[str, str], _PtySession] = {}
_sessions_lock = asyncio.Lock()


def _terminate_process_group(proc: subprocess.Popen[bytes]) -> None:
    """SIGTERM (then SIGKILL) the shell's process group. Blocking — run in executor."""
    try:
        if proc.poll() is not None:
            return
        with contextlib.suppress(ProcessLookupError, OSError):
            posix_compat.killpg(posix_compat.getpgid(proc.pid), signal.SIGTERM)
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError, OSError):
                posix_compat.killpg(
                    posix_compat.getpgid(proc.pid),
                    posix_compat.sigkill(),
                )
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=1)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("terminal process cleanup error: %s", exc)


def _spawn_pty_session(
    sid: str,
    agent_id: str,
    user_id: int,
    workspace_dir: str,
    cols: int,
    rows: int,
    persistent: bool,
) -> _PtySession:
    """Create a PTY pair, spawn the shell at ``workspace_dir`` (pump not started).

    Caller must subscribe then call :meth:`_PtySession.start_pump` so an
    immediately-exiting shell cannot race the empty subscriber set under
    ``_sessions_lock``.
    """
    master_fd, slave_fd = posix_compat.openpty()
    _set_winsize(master_fd, cols, rows)
    posix_compat.set_nonblock(master_fd)

    shell = _detect_shell()
    # Interactive flag so rc files (.bashrc / .zshrc) load.
    # Avoid -l (login shell) for zsh: it triggers logout output ("%" line) on exit.
    cmd = [shell, "-i"] if ("bash" in shell or "zsh" in shell) else [shell]
    env = _shell_env(shell=shell)
    zdotdir: str | None = None
    if "zsh" in shell:
        zdotdir = _zsh_web_zdotdir()
        env["ZDOTDIR"] = zdotdir

    cwd = workspace_dir
    if not os.path.isdir(cwd):
        # Fall back rather than fail the whole WebSocket — mkdir races or a
        # deleted workspace should still yield a usable shell.
        cwd = os.path.expanduser("~") or "/"
        logger.warning(
            "terminal cwd missing, falling back: agent=%s wanted=%s using=%s",
            agent_id,
            workspace_dir,
            cwd,
        )

    proc = subprocess.Popen(
        cmd,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True,
        preexec_fn=posix_compat.setsid,  # separate process group for clean teardown
        env=env,
        cwd=cwd,
    )
    os.close(slave_fd)

    session = _PtySession(
        sid, agent_id, user_id, proc, master_fd, cols, rows, persistent, zdotdir=zdotdir
    )
    logger.info(
        "terminal opened: agent=%s sid=%s pid=%s shell=%s cwd=%s persistent=%s",
        agent_id,
        sid,
        proc.pid,
        shell,
        cwd,
        persistent,
    )
    return session


def _start_session_pump(session: _PtySession) -> None:
    """Begin PTY fan-out after the first subscriber is attached."""
    if session.pump_task is None and not session.closed:
        session.pump_task = asyncio.create_task(_pump_pty(session))


async def _pump_pty(session: _PtySession) -> None:
    """Read PTY output into scrollback and fan out to subscribers.

    Bound to the *session*, not to any single WebSocket, so output keeps
    being captured even while no client is attached.
    """
    while True:
        data = _read_nonblock(session.master_fd)
        if data is None:
            # Would-block. If the shell has exited, stop draining.
            if session.proc.poll() is not None:
                break
            await asyncio.sleep(0.02)
            continue
        if data == b"":
            break  # EOF / read error → shell gone
        session.append_scrollback(data)
        item: dict[str, object] = {"type": "output", "data": data.decode("utf-8", errors="replace")}
        for q in list(session.subscribers):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(item)

    # Shell exited on its own — notify attached clients, then reap the session.
    exit_code = session.proc.poll()
    exit_item: dict[str, object] = {
        "type": "exit",
        "code": exit_code if exit_code is not None else 0,
    }
    for q in list(session.subscribers):
        with contextlib.suppress(asyncio.QueueFull):
            q.put_nowait(exit_item)
    await _destroy_session(session, cancel_pump=False)


async def _destroy_session(session: _PtySession, *, cancel_pump: bool) -> None:
    """Tear down a session: stop the pump, close the PTY, kill the shell.

    Idempotent — the ``closed`` flag makes consecutive calls safe. The
    check-and-set has no ``await`` in between, so within one event loop
    only the first caller proceeds.
    """
    if session.closed:
        return
    session.closed = True

    key = (session.agent_id, session.sid)
    async with _sessions_lock:
        # NOCA:IdenticalIsComparison(intentional object-identity check before registry delete)
        if _sessions.get(key) is session:
            del _sessions[key]

    if session.detach_handle is not None:
        session.detach_handle.cancel()
        session.detach_handle = None

    if cancel_pump and session.pump_task is not None and not session.pump_task.done():
        session.pump_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await session.pump_task

    with contextlib.suppress(OSError):
        os.close(session.master_fd)

    if session.zdotdir:
        shutil.rmtree(session.zdotdir, ignore_errors=True)

    # Kill the whole process group off-thread so we never block the loop.
    proc = session.proc
    if proc.poll() is None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _terminate_process_group, proc)

    logger.info(
        "terminal session ended: agent=%s sid=%s active=%d",
        session.agent_id,
        session.sid,
        len(_sessions),
    )


def _arm_detach_cleanup(session: _PtySession) -> None:
    """Schedule a persistent session for cleanup once the grace period elapses."""
    if session.closed or session.subscribers:
        return
    loop = asyncio.get_running_loop()
    if session.detach_handle is not None:
        session.detach_handle.cancel()

    def _reap() -> None:
        if not session.subscribers and not session.closed:
            # Keep a reference so the deferred task is not garbage-collected.
            session.reap_task = asyncio.ensure_future(_destroy_session(session, cancel_pump=True))

    session.detach_handle = loop.call_later(_DETACH_GRACE_SECONDS, _reap)
    logger.info(
        "terminal detached: agent=%s sid=%s grace=%.0fs",
        session.agent_id,
        session.sid,
        _DETACH_GRACE_SECONDS,
    )


@router.get("/agents/{agent_id}/terminal/context")
async def terminal_context(
    agent_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Return system context for the AI terminal panel."""
    assert server.app_runtime is not None
    row = server.app_runtime.agent_registry.get_row(agent_id)
    if row is None:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, "no agents for user")
    workspace_dir = str(server.services.paths.ensure_agent_workspace(agent_id))

    os_name = platform.system()
    os_release = platform.release()
    machine = platform.machine()
    os_str = f"{os_name} {os_release} {machine}"

    distro = ""
    try:
        if os_name == "Linux":
            import pathlib as _pathlib

            p = _pathlib.Path("/etc/os-release")
            if p.exists():
                for line in p.read_text().splitlines():
                    if line.startswith("PRETTY_NAME="):
                        distro = line.split("=", 1)[1].strip().strip('"')
                        break
    except Exception:
        pass

    supported, unsupported_reason = terminal_supported()
    return {
        "os": os_str,
        "distro": distro,
        "shell": _detect_shell(),
        "hostname": socket.gethostname(),
        "username": os.environ.get("USER") or os.environ.get("USERNAME") or "",
        "workspace_dir": workspace_dir,
        "agent_id": agent_id,
        "agent_name": row.name,
        "terminal_supported": supported,
        "terminal_unsupported_reason": unsupported_reason,
    }


@router.websocket("/agents/{agent_id}/terminal/ws")
async def terminal_ws(
    websocket: WebSocket,
    agent_id: str,
    token: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    cols: int = Query(default=80),
    rows: int = Query(default=24),
) -> None:
    """PTY-backed WebSocket terminal scoped to an agent's workspace.

    Pass ``session_id`` to opt into session persistence (survives disconnect,
    replays history on re-attach). Omit it for an ephemeral shell.
    """
    server = websocket.app.state.octop_server

    # --- auth (token query param + agent ownership) ---------------------
    if not token:
        await websocket.close(code=4001, reason="missing token")
        return
    try:
        user = resolve_user_from_token(server, token)
    except OctopError as exc:
        await websocket.close(code=4001, reason=f"auth: {exc.code.value}")
        return
    assert server.app_runtime is not None
    registry = server.app_runtime.agent_registry
    agent_row = registry.get_row(agent_id)
    if agent_row is None:
        # Allow short suffixes; include disabled agents so terminal works even when
        # the agent runtime is stopped/disabled.
        candidates: list[Any] = []
        agent_repo = getattr(server.services, "agent_repo", None)
        if agent_repo is not None:
            with contextlib.suppress(Exception):
                candidates = list(agent_repo.list_all(include_disabled=True))
        if not candidates:
            with contextlib.suppress(Exception):
                candidates = list(registry.list_rows())
        for row in candidates:
            row_id = str(getattr(row, "agent_id", "") or "")
            if row_id == agent_id or row_id.endswith(agent_id):
                agent_row = row
                agent_id = row_id
                break
    if agent_row is None:
        await websocket.close(code=4404, reason="agent not found")
        return
    workspace_dir = str(server.services.paths.ensure_agent_workspace(agent_id))

    supported, unsupported_reason = terminal_supported()
    if not supported:
        await websocket.accept()
        await websocket.send_text(json.dumps({"type": "error", "message": unsupported_reason}))
        await websocket.close(code=4003, reason="terminal unsupported")
        return

    await websocket.accept()
    logger.info(
        "terminal ws accepted: agent=%s user=%s session_id=%s",
        agent_id,
        user.id,
        session_id or "-",
    )

    # --- resolve session (re-attach vs create) --------------------------
    persistent = bool(session_id and session_id.strip())
    sid = (session_id.strip() if session_id else "") or uuid.uuid4().hex
    key = (agent_id, sid)

    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
    session: _PtySession | None = None
    snapshot: bytes = b""
    is_reattach = False
    cap_exceeded = False
    wrong_owner = False
    spawn_error: str | None = None
    just_spawned = False

    try:
        async with _sessions_lock:
            existing = _sessions.get(key) if persistent else None
            if existing is not None and not existing.closed:
                # Ownership check: only the session's creator may re-attach.
                if existing.user_id != user.id:
                    wrong_owner = True
                else:
                    session = existing
                    is_reattach = True
                    # A client is back — cancel any pending grace cleanup.
                    if existing.detach_handle is not None:
                        existing.detach_handle.cancel()
                        existing.detach_handle = None
            elif not wrong_owner:
                if len(_sessions) >= _MAX_SESSIONS:
                    cap_exceeded = True
                else:
                    try:
                        session = _spawn_pty_session(
                            sid, agent_id, user.id, workspace_dir, cols, rows, persistent
                        )
                        _sessions[key] = session
                        just_spawned = True
                    except Exception as spawn_exc:
                        logger.exception(
                            "terminal spawn failed: agent=%s sid=%s cwd=%s",
                            agent_id,
                            sid,
                            workspace_dir,
                        )
                        spawn_error = str(spawn_exc)
            # Snapshot scrollback, then subscribe — both sync, no await in
            # between, so the pump can neither duplicate nor drop output at
            # the replay/live boundary.
            if session is not None:
                snapshot = bytes(session.scrollback)
                session.subscribers.add(queue)
                # Start the pump only after the first subscriber is attached
                # (and only for newly spawned shells — re-attach keeps the
                # existing pump).
                if just_spawned:
                    _start_session_pump(session)

        if spawn_error is not None:
            await websocket.send_text(
                json.dumps({"type": "error", "message": f"failed to start shell: {spawn_error}"})
            )
            await websocket.close(code=1011, reason="spawn failed")
            return
        if wrong_owner:
            await websocket.send_text(
                json.dumps({"type": "error", "message": "session owned by another user"})
            )
            await websocket.close(code=4033, reason="session owned by another user")
            return
        if cap_exceeded or session is None:
            await websocket.send_text(
                json.dumps({"type": "error", "message": f"too many sessions (max {_MAX_SESSIONS})"})
            )
            await websocket.close(code=4029, reason="too many sessions")
            return

        logger.info(
            "terminal %s: agent=%s sid=%s active=%d",
            "re-attached" if is_reattach else "started",
            agent_id,
            sid,
            len(_sessions),
        )

        # Apply this client's current window size to the (shared) PTY.
        session.cols, session.rows = cols, rows
        if not session.closed:
            _set_winsize(session.master_fd, cols, rows)

        # Persistent sessions carry session metadata + scrollback replay so
        # the client can resume. Ephemeral sessions only stream live output,
        # preserving the original wire protocol for existing clients.
        if persistent:
            await websocket.send_text(
                json.dumps({"type": "session", "session_id": sid, "agent_id": agent_id})
            )
            if snapshot:
                await websocket.send_text(
                    json.dumps(
                        {"type": "history", "data": snapshot.decode("utf-8", errors="replace")}
                    )
                )

        async def writer() -> None:
            """Drain the fan-out queue into this WebSocket."""
            while True:
                item = await queue.get()
                if websocket.application_state != WebSocketState.CONNECTED:
                    break
                try:
                    await websocket.send_text(json.dumps(item))
                except WebSocketDisconnect:
                    break
                except Exception as exc:  # pragma: no cover - defensive
                    logger.debug("terminal send failed (sid=%s): %s", sid, exc)
                    break
                if item.get("type") == "exit":
                    break

        async def reader() -> None:
            """Forward client input / resize frames to the PTY."""
            while True:
                try:
                    raw = await websocket.receive_text()
                except WebSocketDisconnect:
                    return
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                kind = msg.get("type")
                if kind == "input":
                    data = msg.get("data", "")
                    if isinstance(data, str) and not session.closed:
                        try:
                            os.write(session.master_fd, data.encode("utf-8"))
                        except OSError:
                            return
                elif kind == "close":
                    # Client closed the tab — reap the shell now instead of
                    # leaving it in the detach grace window.
                    if not session.closed:
                        await _destroy_session(session, cancel_pump=True)
                    return
                elif kind == "resize":
                    if not session.closed:
                        try:
                            new_cols = int(msg.get("cols") or 80)
                            new_rows = int(msg.get("rows") or 24)
                        except (TypeError, ValueError):
                            continue
                        session.cols, session.rows = new_cols, new_rows
                        _set_winsize(session.master_fd, new_cols, new_rows)

        # Race reader vs writer; whichever finishes first triggers shutdown
        # (matches the original proactive-close behaviour when the shell exits).
        writer_task = asyncio.create_task(writer())
        reader_task = asyncio.create_task(reader())
        done, pending = await asyncio.wait(
            {writer_task, reader_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t
        # Surface no "Task exception was never retrieved" warnings.
        for t in done:
            with contextlib.suppress(Exception):
                t.result()
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("terminal session failed")
        if websocket.application_state == WebSocketState.CONNECTED:
            with contextlib.suppress(WebSocketDisconnect):
                await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
    finally:
        close_sid = sid if "sid" in locals() else (session_id or "-")
        logger.info(
            "terminal ws closing: agent=%s sid=%s persistent=%s",
            agent_id,
            close_sid,
            bool(session.persistent) if session is not None else False,
        )
        # Detach this connection. Persistent shells are kept alive for the
        # grace period so a reconnect can re-attach; ephemeral shells are
        # reaped immediately (original behaviour).
        if session is not None:
            session.subscribers.discard(queue)
            if not session.closed and not session.subscribers:
                if session.persistent:
                    _arm_detach_cleanup(session)
                else:
                    await _destroy_session(session, cancel_pump=True)
        if websocket.application_state == WebSocketState.CONNECTED:
            with contextlib.suppress(Exception):
                await websocket.close()
        logger.info("terminal websocket closed: agent=%s sid=%s", agent_id, close_sid)


def _read_nonblock(fd: int | None) -> bytes | None:
    """Return ``bytes`` read, ``None`` if would-block, ``b""`` on EOF."""
    if fd is None:
        return b""
    try:
        return os.read(fd, 4096)
    except OSError as exc:
        if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
            return None
        return b""


def _stub() -> Any:
    """Internal helper kept for tests; real flows live above."""
    return None
