"""The mobile surface must not run adb / docker probes on the event loop.

``mobile_status()`` shells out to ``adb devices`` and ``docker inspect``, each with a 5 s timeout,
and ``list_devices()`` re-runs the adb probe. Sibling call sites already offload them
(``shell_ws.py:84``, ``tools.py:66``, and ``status.py``'s own ``device_info``), so the remaining
on-loop calls are the defect this file pins.
"""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.websockets import WebSocketState

from octop.api.routers.mobile import status as status_router
from octop.api.routers.mobile import stream as stream_router
from octop.infra.mobile.agent_control import set_mobile_agent_control
from octop.infra.mobile.setup import MobileStatus

_LOOP_BLOCKED_S = 5.0


def _status(*, devices: tuple[str, ...] = ()) -> MobileStatus:
    return MobileStatus(
        ok=True,
        mobile_supported=True,
        setup_state="ready",
        backend="physical",
        platform="linux",
        reason="",
        adb_available=True,
        adb_path="/usr/bin/adb",
        devices=devices,
        selected_device=devices[0] if devices else None,
        container_running=False,
    )


def _server() -> Any:
    return SimpleNamespace(services=SimpleNamespace(config=None))


class _ThreadRecorder:
    """Probe double that remembers whether it was handed a worker thread or the loop's thread."""

    def __init__(self, result: Any) -> None:
        self.result = result
        self.ran_on_main_thread: bool | None = None
        self.calls = 0

    def __call__(self, *_args: Any, **_kwargs: Any) -> Any:
        self.calls += 1
        self.ran_on_main_thread = threading.current_thread() is threading.main_thread()
        return self.result


@pytest.fixture(autouse=True)
def _reset_agent_control() -> Any:
    set_mobile_agent_control(enabled=False, device=None)
    yield
    set_mobile_agent_control(enabled=False, device=None)


async def test_status_endpoint_offloads_the_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = _ThreadRecorder(_status(devices=("emulator-5554",)))
    monkeypatch.setattr(status_router, "mobile_status", probe)

    payload = await status_router.get_mobile_status(None, _server(), None)  # type: ignore[arg-type]

    assert probe.calls == 1
    assert probe.ran_on_main_thread is False
    assert payload["devices"] == ["emulator-5554"]


async def test_status_endpoint_keeps_the_loop_running_while_adb_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A slow ``adb devices`` must not freeze every other coroutine on the loop."""
    release = threading.Event()
    ticks = 0
    ticks_seen_by_probe: list[int] = []

    def blocking_probe(*_args: Any, **_kwargs: Any) -> MobileStatus:
        release.wait(timeout=_LOOP_BLOCKED_S)
        ticks_seen_by_probe.append(ticks)
        return _status()

    async def heartbeat() -> None:
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.01)

    async def releaser() -> None:
        await asyncio.sleep(0.05)
        release.set()

    monkeypatch.setattr(status_router, "mobile_status", blocking_probe)
    beat = asyncio.create_task(heartbeat())
    unlock = asyncio.create_task(releaser())
    try:
        await status_router.get_mobile_status(None, _server(), None)  # type: ignore[arg-type]
    finally:
        release.set()
        beat.cancel()
        unlock.cancel()

    # Only loop-scheduled work can release the probe, so a non-zero tick count is proof the loop
    # stayed free. On the event-loop path the coroutine blocks before yielding, the releaser never
    # runs, and the probe returns when its own timeout expires having seen no ticks at all.
    assert ticks_seen_by_probe and ticks_seen_by_probe[0] > 0


async def test_device_info_offloads_the_connected_devices_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = _ThreadRecorder(["emulator-5554"])
    monkeypatch.setattr(status_router, "device_info", lambda _serial: {})
    monkeypatch.setattr(status_router, "list_devices", probe)

    info = await status_router.get_mobile_device_info("emulator-5554", None)  # type: ignore[arg-type]

    assert probe.calls == 1
    assert probe.ran_on_main_thread is False
    assert info == {}


async def test_agent_control_put_offloads_the_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = _ThreadRecorder(["emulator-5554"])
    monkeypatch.setattr(status_router, "list_devices", probe)
    body = status_router.MobileAgentControlBody(enabled=True, device="emulator-5554")

    payload = await status_router.put_agent_control(body, None)  # type: ignore[arg-type]

    assert probe.ran_on_main_thread is False
    assert payload["device"] == "emulator-5554"


class _FakeStreamWS:
    """WebSocket double covering just what ``mobile_stream_ws`` touches before it bails out."""

    def __init__(self, start_payload: str) -> None:
        self.application_state = WebSocketState.CONNECTING
        self.sent: list[str] = []
        self.closed: tuple[int, str] | None = None
        self._start_payload = start_payload
        self.app = SimpleNamespace(state=SimpleNamespace(octop_server=_server()))
        self.headers: dict[str, str] = {}

    async def accept(self) -> None:
        self.application_state = WebSocketState.CONNECTED

    async def receive_text(self) -> str:
        return self._start_payload

    async def send_text(self, payload: str) -> None:
        self.sent.append(payload)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = (code, reason)
        self.application_state = WebSocketState.DISCONNECTED


async def test_stream_ws_offloads_both_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    status_probe = _ThreadRecorder(_status())
    devices_probe = _ThreadRecorder([])
    monkeypatch.setattr(stream_router, "mobile_status", status_probe)
    monkeypatch.setattr(stream_router, "list_devices", devices_probe)
    monkeypatch.setattr(stream_router, "resolve_user_from_token", lambda *_a: object())
    monkeypatch.setattr(stream_router, "user_has_permission", lambda *_a: True)

    ws = _FakeStreamWS('{"type": "start", "token": "t"}')
    await stream_router.mobile_stream_ws(ws, None)  # type: ignore[arg-type]

    assert status_probe.ran_on_main_thread is False
    assert devices_probe.ran_on_main_thread is False
    # No device attached: the handler must report it and close, having asked adb off the loop.
    assert ws.sent and "no adb device" in ws.sent[0]
    assert ws.closed == (4003, "no device")
