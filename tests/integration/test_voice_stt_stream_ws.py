"""Realtime (streaming) Tencent STT WebSocket."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from starlette.websockets import WebSocketDisconnect

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.voice import realtime
from octop.infra.voice.manager import VoiceManager
from octop.infra.voice.realtime import RealtimeEvent
from tests.support.app import octop_client
from tests.support.auth import auth_header, bootstrap_admin
from tests.support.http import ws_connect, ws_token

TENCENT_REALTIME_EXTRA = {
    "secret_id": "sid",
    "secret_key": "skey",
    "region": "ap-guangzhou",
    "realtime_stt": True,
    "app_id": "1302566622",
}


@pytest.fixture
async def env(tmp_octop_home: Path) -> AsyncIterator[Any]:
    async with octop_client(tmp_octop_home) as (c, srv):
        await bootstrap_admin(c, tmp_octop_home)
        yield c, srv, await auth_header(c)


def _manager(srv: Any) -> VoiceManager:
    return VoiceManager(
        settings_repo=srv.services.settings_repo,
        voice_provider_repo=srv.services.voice_provider_repo,
    )


def _enable_realtime(srv: Any, extra: dict[str, object] | None = None) -> None:
    srv.services.voice_provider_repo.create(
        name="tencent",
        kind="tencent",
        capability="both",
        api_key="sid:skey",
        extra_json=json.dumps(TENCENT_REALTIME_EXTRA if extra is None else extra),
    )
    _manager(srv).set_active(stt="tencent")


def _stream_ws(c: Any, auth: dict[str, str] | None = None) -> Any:
    query = f"?token={ws_token(auth)}&locale=zh" if auth else "?locale=zh"
    return ws_connect(c._octop_app, f"/api/voice/stt-stream{query}")


class FakeSession:
    """Stands in for the upstream Tencent connection."""

    def __init__(
        self,
        frames: list[RealtimeEvent],
        *,
        connect_error: OctopError | None = None,
    ) -> None:
        self._frames = frames
        self._connect_error = connect_error
        self.audio: list[bytes] = []
        self.finished = False
        self.closed = False
        self.opened = False

    async def connect(self) -> None:
        if self._connect_error is not None:
            raise self._connect_error
        self.opened = True

    async def send_audio(self, pcm: bytes) -> None:
        self.audio.append(pcm)

    async def finish(self) -> None:
        self.finished = True

    async def events(self) -> AsyncIterator[RealtimeEvent]:
        for frame in self._frames:
            yield frame

    async def close(self) -> None:
        self.closed = True


def _install_fake_session(
    monkeypatch: pytest.MonkeyPatch,
    frames: list[RealtimeEvent],
    *,
    connect_error: OctopError | None = None,
) -> FakeSession:
    session = FakeSession(frames, connect_error=connect_error)
    monkeypatch.setattr(realtime, "open_session", lambda _config: session)
    return session


def _sentence(text: str, *, final: bool, sentence_id: int = 0) -> RealtimeEvent:
    return RealtimeEvent(kind="final" if final else "interim", text=text, sentence_id=sentence_id)


async def test_missing_token_is_rejected(env: Any) -> None:
    c, _srv, _auth = env
    with pytest.raises(WebSocketDisconnect):
        async with _stream_ws(c):
            pass


async def test_streams_audio_and_relays_results(env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    c, srv, auth = env
    _enable_realtime(srv)
    session = _install_fake_session(
        monkeypatch,
        [
            _sentence("你好", final=False),
            _sentence("你好世界", final=True),
            RealtimeEvent(kind="done"),
        ],
    )

    async with _stream_ws(c, auth) as ws:
        assert await ws.receive_json() == {"type": "ready"}
        await ws.send_bytes(b"\x00" * 1280)
        await ws.send_bytes(b"\x01" * 1280)
        await ws.send_json({"type": "end"})
        frames = await ws.drain_turn()

    assert frames == [
        {"type": "interim", "text": "你好", "sentence_id": 0},
        {"type": "final", "text": "你好世界", "sentence_id": 0},
        {"type": "done"},
    ]
    assert session.audio == [b"\x00" * 1280, b"\x01" * 1280]
    assert session.finished is True
    assert session.closed is True


async def test_realtime_must_be_configured(env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    c, srv, auth = env
    _install_fake_session(monkeypatch, [])

    async with _stream_ws(c, auth) as ws:
        frame = await ws.receive_json()
        assert frame["type"] == "error"
        assert frame["code"] == ErrorCode.VOICE_REALTIME_UNAVAILABLE.value
        with pytest.raises(WebSocketDisconnect):
            await ws.receive_json()


async def test_upstream_handshake_failure_is_reported(
    env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    c, srv, auth = env
    _enable_realtime(srv)
    _install_fake_session(
        monkeypatch,
        [],
        connect_error=OctopError(
            ErrorCode.VOICE_REALTIME_UNAVAILABLE,
            "handshake failed",
            details={"tencent_code": 4003},
        ),
    )

    async with _stream_ws(c, auth) as ws:
        frame = await ws.receive_json()
        assert frame["type"] == "error"
        assert frame["tencent_code"] == 4003
        assert "实时语音识别" in frame["message"]


async def test_upstream_stream_error_is_forwarded(
    env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    c, srv, auth = env
    _enable_realtime(srv)
    _install_fake_session(monkeypatch, [RealtimeEvent(kind="error", error_code=4004)])

    async with _stream_ws(c, auth) as ws:
        assert await ws.receive_json() == {"type": "ready"}
        await ws.send_bytes(b"\x00" * 1280)

        error = await ws.receive_json()
        assert error["type"] == "error"
        assert error["code"] == ErrorCode.VOICE_REALTIME_UNAVAILABLE.value
        assert error["tencent_code"] == 4004
        assert "资源包" in error["message"]
        assert await ws.receive_json() == {"type": "done"}
