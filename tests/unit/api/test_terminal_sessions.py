"""Unit tests for the terminal session machinery and WS handler.

These run without the full ``OctopServer`` / ``harness_gateway`` stack:
the ``terminal`` router module imports cleanly on its own, so we drive
it with lightweight fakes for the server, the WebSocket and the PTY
spawn. Pure-logic cases run on any platform; PTY-path cases are gated
on POSIX (the dashboard terminal is POSIX-only).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import WebSocketDisconnect
from starlette.websockets import WebSocketState

from octop.api.routers import terminal
from octop.infra.errors import ErrorCode, OctopError

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX terminal required")


def _make_session(
    sid: str,
    agent_id: str,
    user_id: int,
    persistent: bool,
    *,
    scrollback: bytes = b"",
    cols: int = 80,
    rows: int = 24,
    master_fd: int | None = None,
) -> terminal._PtySession:
    """Build a real ``_PtySession`` backed by a mock process + a real fd.

    ``proc.poll()`` returns 0 (exited) so ``_destroy_session`` skips the
    process-group kill / executor path — teardown stays synchronous and
    no real subprocess is touched.
    """
    fd = master_fd if master_fd is not None else os.open(os.devnull, os.O_RDWR)
    proc = Mock()
    proc.poll.return_value = 0
    proc.pid = 99999
    proc.returncode = 0
    session = terminal._PtySession(sid, agent_id, user_id, proc, fd, cols, rows, persistent)
    session.scrollback = bytearray(scrollback)
    return session


@pytest.fixture(autouse=True)
def _reset_terminal_state():
    """Isolate each test: fresh registry + fresh lock bound to this loop.

    The module-level ``_sessions_lock`` would otherwise bind to the first
    test's event loop and break subsequent ones; recreating it per test
    keeps each test's loop self-contained.
    """
    terminal._sessions.clear()
    terminal._sessions_lock = asyncio.Lock()
    yield
    for s in list(terminal._sessions.values()):
        if isinstance(s, terminal._PtySession):
            if s.detach_handle is not None:
                s.detach_handle.cancel()
            if not s.closed:
                s.closed = True
                with contextlib.suppress(OSError):
                    os.close(s.master_fd)
    terminal._sessions.clear()


# ---------------------------------------------------------------------------
# Pure session logic
# ---------------------------------------------------------------------------


def test_scrollback_trims_to_max() -> None:
    session = _make_session("s1", "agent", 1, persistent=True)
    session.append_scrollback(b"x" * (terminal._MAX_SCROLLBACK_BYTES + 100))
    assert len(session.scrollback) == terminal._MAX_SCROLLBACK_BYTES
    # Trimming drops the oldest bytes; the tail (most recent) is preserved.
    assert bytes(session.scrollback).endswith(b"x" * 100)


def test_scrollback_preserves_order_under_limit() -> None:
    session = _make_session("s1", "agent", 1, persistent=True)
    session.append_scrollback(b"abc")
    session.append_scrollback(b"def")
    assert bytes(session.scrollback) == b"abcdef"


def test_session_defaults() -> None:
    session = _make_session("s1", "agent", 1, persistent=False)
    assert session.closed is False
    assert session.subscribers == set()
    assert session.pump_task is None
    assert session.detach_handle is None
    assert session.persistent is False


def test_sessions_keyed_by_agent_and_sid() -> None:
    # Same sid, different agent -> two distinct sessions (no cross-agent leak).
    a = _make_session("sid", "agent-a", 1, persistent=True)
    b = _make_session("sid", "agent-b", 1, persistent=True)
    terminal._sessions[("agent-a", "sid")] = a
    terminal._sessions[("agent-b", "sid")] = b
    assert terminal._sessions[("agent-a", "sid")] is a
    assert terminal._sessions[("agent-b", "sid")] is b
    assert len(terminal._sessions) == 2


async def test_destroy_session_is_idempotent() -> None:
    session = _make_session("s1", "agent", 1, persistent=False)
    terminal._sessions[("agent", "s1")] = session
    await terminal._destroy_session(session, cancel_pump=True)
    assert session.closed is True
    assert ("agent", "s1") not in terminal._sessions
    # Second call is a no-op (fd already closed, already unregistered).
    await terminal._destroy_session(session, cancel_pump=True)
    assert ("agent", "s1") not in terminal._sessions


async def test_arm_detach_cleanup_skips_when_subscribers_present() -> None:
    session = _make_session("s1", "agent", 1, persistent=True)
    terminal._sessions[("agent", "s1")] = session
    session.subscribers.add(asyncio.Queue())
    terminal._arm_detach_cleanup(session)
    assert session.detach_handle is None  # not armed while a client is attached


async def test_arm_detach_cleanup_arms_when_empty() -> None:
    session = _make_session("s1", "agent", 1, persistent=True)
    terminal._sessions[("agent", "s1")] = session
    terminal._arm_detach_cleanup(session)
    assert session.detach_handle is not None
    session.detach_handle.cancel()  # don't actually wait for the grace period


@posix_only
async def test_pump_pty_drains_fans_out_and_reaps() -> None:
    r, w = os.pipe()
    proc = Mock()
    proc.poll.return_value = 0
    session = terminal._PtySession("s1", "agent", 1, proc, r, 80, 24, persistent=True)
    terminal._sessions[("agent", "s1")] = session
    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
    session.subscribers.add(queue)

    os.write(w, b"hello\n")
    os.close(w)

    await terminal._pump_pty(session)

    assert bytes(session.scrollback) == b"hello\n"
    out = await queue.get()
    assert out == {"type": "output", "data": "hello\n"}
    exit_item = await queue.get()
    assert exit_item == {"type": "exit", "code": 0}
    assert session.closed is True
    assert ("agent", "s1") not in terminal._sessions


# ---------------------------------------------------------------------------
# WS handler driven with fakes (no real PTY, no OctopServer)
# ---------------------------------------------------------------------------


class _FakeWS:
    """Minimal starlette-WebSocket stand-in for the terminal handler."""

    def __init__(self, server: object, received: tuple[str, ...] = ()) -> None:
        self.app = SimpleNamespace(state=SimpleNamespace(octop_server=server))
        self.application_state = WebSocketState.CONNECTING
        self._received = list(received)
        self.sent: list[str] = []
        self.close_code: int | None = None
        self.accepted = False

    async def accept(self) -> None:
        self.accepted = True
        self.application_state = WebSocketState.CONNECTED

    async def send_text(self, text: str) -> None:
        self.sent.append(text)

    async def receive_text(self) -> str:
        if not self._received:
            raise WebSocketDisconnect()
        return self._received.pop(0)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.close_code = code
        self.application_state = WebSocketState.DISCONNECTED


def _make_server(*, has_agent: bool = True) -> tuple[object, Mock]:
    get_row = Mock(return_value=SimpleNamespace(name="bot") if has_agent else None)
    server = SimpleNamespace(
        app_runtime=SimpleNamespace(agent_registry=SimpleNamespace(get_row=get_row)),
        services=SimpleNamespace(
            paths=SimpleNamespace(ensure_agent_workspace=lambda _aid: "/tmp/ws")
        ),
    )
    return server, get_row


def _sent_messages(ws: _FakeWS) -> list[dict[str, object]]:
    return [json.loads(t) for t in ws.sent]


def _patch_user(monkeypatch, user_id: int = 1) -> None:
    monkeypatch.setattr(
        terminal, "resolve_user_from_token", lambda _s, _t: SimpleNamespace(id=user_id)
    )


def _patch_spawn(monkeypatch, spawned: list[terminal._PtySession]) -> None:
    def fake_spawn(sid, agent_id, user_id, workspace_dir, cols, rows, persistent):
        s = _make_session(sid, agent_id, user_id, persistent)
        # Keep the mock process "alive" so a started pump would not reap it;
        # tests still stub the pump out below.
        s.proc.poll.return_value = None
        spawned.append(s)
        return s

    monkeypatch.setattr(terminal, "_spawn_pty_session", fake_spawn)
    # Avoid driving a real pump against the fake /dev/null master fd.
    monkeypatch.setattr(terminal, "_start_session_pump", lambda _s: None)


async def test_ws_missing_token_closes_4001(monkeypatch) -> None:
    server, _ = _make_server()
    ws = _FakeWS(server)
    await terminal.terminal_ws(ws, agent_id="a1", token=None, cols=80, rows=24)
    assert ws.close_code == 4001
    assert not ws.accepted


async def test_ws_bad_token_closes_4001(monkeypatch) -> None:
    server, _ = _make_server()

    def _bad(_server, _token):
        raise OctopError(ErrorCode.AUTH_FAILED, "nope")

    monkeypatch.setattr(terminal, "resolve_user_from_token", _bad)
    ws = _FakeWS(server)
    await terminal.terminal_ws(ws, agent_id="a1", token="bad", cols=80, rows=24)
    assert ws.close_code == 4001


async def test_ws_agent_not_found_closes_4404(monkeypatch) -> None:
    server, _ = _make_server(has_agent=False)
    _patch_user(monkeypatch)
    ws = _FakeWS(server)
    await terminal.terminal_ws(ws, agent_id="a1", token="ok", cols=80, rows=24)
    assert ws.close_code == 4404


async def test_ws_unsupported_platform_closes_4003(monkeypatch) -> None:
    server, _ = _make_server()
    _patch_user(monkeypatch)
    monkeypatch.setattr(terminal, "terminal_supported", lambda: (False, "nope"))
    ws = _FakeWS(server)
    await terminal.terminal_ws(ws, agent_id="a1", token="ok", cols=80, rows=24)
    assert ws.close_code == 4003
    msgs = _sent_messages(ws)
    assert msgs and msgs[0]["type"] == "error"


@posix_only
async def test_ws_ephemeral_session_created_and_reaped(monkeypatch) -> None:
    server, _ = _make_server()
    _patch_user(monkeypatch)
    spawned: list[terminal._PtySession] = []
    _patch_spawn(monkeypatch, spawned)

    ws = _FakeWS(server)  # receive_text disconnects immediately
    # session_id=None opts into the ephemeral path (original behaviour).
    await terminal.terminal_ws(ws, agent_id="a1", token="ok", session_id=None, cols=80, rows=24)

    assert len(spawned) == 1
    assert spawned[0].persistent is False
    # Ephemeral: no session/history messages on the wire.
    assert all(m["type"] not in ("session", "history") for m in _sent_messages(ws))
    # Reaped immediately on disconnect (original behaviour).
    assert spawned[0].closed is True
    assert ("a1", spawned[0].sid) not in terminal._sessions


@posix_only
async def test_ws_persistent_session_emits_session_message(monkeypatch) -> None:
    server, _ = _make_server()
    _patch_user(monkeypatch)
    spawned: list[terminal._PtySession] = []
    _patch_spawn(monkeypatch, spawned)

    ws = _FakeWS(server)
    await terminal.terminal_ws(
        ws, agent_id="a1", token="ok", session_id="my-sid", cols=100, rows=30
    )

    assert len(spawned) == 1
    assert spawned[0].persistent is True
    msgs = _sent_messages(ws)
    session_msg = next(m for m in msgs if m["type"] == "session")
    assert session_msg["session_id"] == "my-sid"
    assert session_msg["agent_id"] == "a1"
    # No history replay on first attach (empty scrollback).
    assert not any(m["type"] == "history" for m in msgs)
    # Persistent: kept alive (grace armed), not destroyed on disconnect.
    assert spawned[0].closed is False
    assert spawned[0].detach_handle is not None
    assert ("a1", "my-sid") in terminal._sessions


@posix_only
async def test_ws_persistent_resume_replays_history(monkeypatch) -> None:
    server, _ = _make_server()
    _patch_user(monkeypatch)

    def _fail_spawn(*a, **k):
        raise AssertionError("spawn must not run on re-attach")

    monkeypatch.setattr(terminal, "_spawn_pty_session", _fail_spawn)
    existing = _make_session("my-sid", "a1", 1, persistent=True, scrollback=b"prior output")
    terminal._sessions[("a1", "my-sid")] = existing

    ws = _FakeWS(server)
    await terminal.terminal_ws(ws, agent_id="a1", token="ok", session_id="my-sid", cols=80, rows=24)

    msgs = _sent_messages(ws)
    session_msg = next(m for m in msgs if m["type"] == "session")
    assert session_msg["session_id"] == "my-sid"
    history_msg = next(m for m in msgs if m["type"] == "history")
    assert history_msg["data"] == "prior output"
    # Same shell re-attached and still alive.
    assert existing.closed is False
    assert existing.detach_handle is not None
    assert terminal._sessions[("a1", "my-sid")] is existing


@posix_only
async def test_ws_resume_wrong_owner_rejected(monkeypatch) -> None:
    server, _ = _make_server()
    # Connecting user is id=1; the session was created by user 999.
    _patch_user(monkeypatch, user_id=1)

    def _fail_spawn(*a, **k):
        raise AssertionError("spawn must not run for a foreign session")

    monkeypatch.setattr(terminal, "_spawn_pty_session", _fail_spawn)
    existing = _make_session("my-sid", "a1", 999, persistent=True)
    terminal._sessions[("a1", "my-sid")] = existing

    ws = _FakeWS(server)
    await terminal.terminal_ws(ws, agent_id="a1", token="ok", session_id="my-sid", cols=80, rows=24)
    assert ws.close_code == 4033
    msgs = _sent_messages(ws)
    assert any(m.get("type") == "error" and "another user" in str(m.get("message")) for m in msgs)
    # Foreign session left untouched.
    assert existing.closed is False
    assert terminal._sessions[("a1", "my-sid")] is existing


@posix_only
async def test_ws_cap_exceeded_closes_4029(monkeypatch) -> None:
    server, _ = _make_server()
    _patch_user(monkeypatch)

    def _fail_spawn(*a, **k):
        raise AssertionError("spawn must not run when the cap is reached")

    monkeypatch.setattr(terminal, "_spawn_pty_session", _fail_spawn)
    # Fill the registry to the hard cap.
    for i in range(terminal._MAX_SESSIONS):
        terminal._sessions[("a1", f"other-{i}")] = _make_session(
            f"other-{i}", "a1", 1, persistent=True
        )

    ws = _FakeWS(server)
    await terminal.terminal_ws(
        ws, agent_id="a1", token="ok", session_id="new-sid", cols=80, rows=24
    )
    assert ws.close_code == 4029
    msgs = _sent_messages(ws)
    assert any(m.get("type") == "error" and "too many" in str(m.get("message")) for m in msgs)
    # Registry untouched: cap sessions still there, new-sid not added.
    assert len(terminal._sessions) == terminal._MAX_SESSIONS
    assert ("a1", "new-sid") not in terminal._sessions


@posix_only
async def test_ws_resize_updates_session_dims(monkeypatch) -> None:
    server, _ = _make_server()
    _patch_user(monkeypatch)
    spawned: list[terminal._PtySession] = []
    _patch_spawn(monkeypatch, spawned)

    resize_frame = json.dumps({"type": "resize", "cols": 120, "rows": 40})
    ws = _FakeWS(server, received=(resize_frame,))
    await terminal.terminal_ws(ws, agent_id="a1", token="ok", session_id="r1", cols=80, rows=24)
    assert spawned[0].cols == 120
    assert spawned[0].rows == 40


def test_detect_shell_cmd_no_login_flag(monkeypatch) -> None:
    """Shell command must NOT include -l (login flag) to avoid trailing '%' on zsh exit."""
    import shutil

    if os.name != "posix":
        pytest.skip("POSIX shells only")

    for shell_name in ("bash", "zsh"):
        shell_path = shutil.which(shell_name)
        if shell_path is None:
            continue  # skip if not installed
        monkeypatch.setenv("SHELL", shell_path)
        shell = terminal._detect_shell()
        cmd = [shell, "-i"] if ("bash" in shell or "zsh" in shell) else [shell]
        assert "-l" not in cmd, f"{shell_name}: -l must not appear in shell cmd"
        assert "-i" in cmd, f"{shell_name}: -i must be present"


@posix_only
async def test_ws_input_frame_writes_to_pty_fd(monkeypatch) -> None:
    server, _ = _make_server()
    _patch_user(monkeypatch)
    r, w = os.pipe()  # master_fd = write end; read the input back from r.
    spawned: list[terminal._PtySession] = []

    def fake_spawn(sid, agent_id, user_id, workspace_dir, cols, rows, persistent):
        s = _make_session(sid, agent_id, user_id, persistent, master_fd=w)
        s.proc.poll.return_value = None
        spawned.append(s)
        return s

    monkeypatch.setattr(terminal, "_spawn_pty_session", fake_spawn)
    monkeypatch.setattr(terminal, "_start_session_pump", lambda _s: None)

    frame = json.dumps({"type": "input", "data": "echo hi\n"})
    ws = _FakeWS(server, received=(frame,))
    await terminal.terminal_ws(ws, agent_id="a1", token="ok", session_id="i1", cols=80, rows=24)
    # The input frame was forwarded to the PTY master fd.
    assert os.read(r, 1024) == b"echo hi\n"
    os.close(r)
    # w is closed by the per-test teardown via session.master_fd.


@posix_only
async def test_ws_close_message_destroys_session(monkeypatch) -> None:
    server, _ = _make_server()
    _patch_user(monkeypatch)
    spawned: list[terminal._PtySession] = []
    _patch_spawn(monkeypatch, spawned)

    close_frame = json.dumps({"type": "close"})
    ws = _FakeWS(server, received=(close_frame,))
    await terminal.terminal_ws(ws, agent_id="a1", token="ok", session_id="c1", cols=80, rows=24)
    # The close frame reaps the shell immediately (no detach grace).
    assert spawned[0].closed is True
    assert ("a1", "c1") not in terminal._sessions
