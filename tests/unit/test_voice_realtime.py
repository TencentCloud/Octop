"""Unit tests for the Tencent realtime ASR upstream session."""

from __future__ import annotations

import json
from typing import Any

import pytest
import websockets.asyncio.client as ws_client
from websockets.exceptions import ConnectionClosed

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.voice import realtime
from octop.infra.voice.realtime import RealtimeEvent

CONFIG = realtime.RealtimeConfig(app_id="1302566622", secret_id="sid", secret_key="skey")


class FakeConnection:
    def __init__(self, frames: list[Any]) -> None:
        self._frames = list(frames)
        self.sent: list[Any] = []
        self.closed = False

    async def recv(self) -> Any:
        if not self._frames:
            raise ConnectionClosed(None, None)
        return self._frames.pop(0)

    async def send(self, payload: Any) -> None:
        self.sent.append(payload)

    async def close(self) -> None:
        self.closed = True


def _patch_connect(
    monkeypatch: pytest.MonkeyPatch,
    connection: FakeConnection | None,
    *,
    error: Exception | None = None,
    capture: list[tuple[str, dict[str, Any]]] | None = None,
) -> None:
    async def fake_connect(url: str, **kwargs: Any) -> FakeConnection:
        if capture is not None:
            capture.append((url, kwargs))
        if error is not None:
            raise error
        assert connection is not None
        return connection

    monkeypatch.setattr(ws_client, "connect", fake_connect)


def _handshake(code: int = 0, message: str = "success") -> str:
    return json.dumps({"code": code, "message": message, "voice_id": "v"})


@pytest.mark.asyncio
async def test_connect_signs_the_url_and_accepts_the_handshake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = FakeConnection([_handshake()])
    capture: list[tuple[str, dict[str, Any]]] = []
    _patch_connect(monkeypatch, conn, capture=capture)

    session = realtime.open_session(CONFIG)
    await session.connect()

    url, kwargs = capture[0]
    assert url.startswith("wss://asr.cloud.tencent.com/asr/v2/1302566622?")
    assert "engine_model_type=16k_zh_en_2.0" in url
    assert "voice_format=1" in url
    assert "&signature=" in url
    assert kwargs["proxy"] is None
    assert kwargs["ping_interval"] is None
    assert session.connected is True


@pytest.mark.asyncio
async def test_connect_maps_a_tencent_error_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = FakeConnection([_handshake(4003, "service is not open")])
    _patch_connect(monkeypatch, conn)

    session = realtime.open_session(CONFIG)
    with pytest.raises(OctopError) as excinfo:
        await session.connect()

    assert excinfo.value.code == ErrorCode.VOICE_REALTIME_UNAVAILABLE
    assert excinfo.value.details["tencent_code"] == 4003
    assert conn.closed is True
    assert session.connected is False


@pytest.mark.asyncio
async def test_connect_rejects_an_unexpected_handshake_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = FakeConnection(["definitely not json"])
    _patch_connect(monkeypatch, conn)

    session = realtime.open_session(CONFIG)
    with pytest.raises(OctopError) as excinfo:
        await session.connect()

    assert excinfo.value.code == ErrorCode.VOICE_REALTIME_UNAVAILABLE
    assert "unexpected handshake" in excinfo.value.message


@pytest.mark.asyncio
async def test_connect_wraps_transport_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_connect(monkeypatch, None, error=OSError("network down"))

    session = realtime.open_session(CONFIG)
    with pytest.raises(OctopError) as excinfo:
        await session.connect()

    assert excinfo.value.code == ErrorCode.VOICE_REALTIME_UNAVAILABLE
    assert "network down" in excinfo.value.message


@pytest.mark.asyncio
async def test_audio_and_end_frames_are_forwarded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = FakeConnection([_handshake()])
    _patch_connect(monkeypatch, conn)

    session = realtime.open_session(CONFIG)
    await session.connect()
    await session.send_audio(b"\x00" * 1280)
    await session.finish()

    assert conn.sent[0] == b"\x00" * 1280
    assert json.loads(conn.sent[1]) == {"type": "end"}


@pytest.mark.asyncio
async def test_send_before_connect_is_a_noop() -> None:
    session = realtime.open_session(CONFIG)

    await session.send_audio(b"\x00" * 1280)
    await session.finish()
    await session.close()


@pytest.mark.asyncio
async def test_events_yields_only_recognized_frames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = FakeConnection(
        [
            _handshake(),  # consumed by connect()
            b"\x00\x01\x02",  # binary frames are not control events
            "not json",
            json.dumps({"code": 0, "unrelated": {}}),
            json.dumps(_result_frame("你好", slice_type=0)),
            json.dumps({"code": 0, "final": 1}),
        ]
    )
    _patch_connect(monkeypatch, conn)

    session = realtime.open_session(CONFIG)
    await session.connect()
    events = [event async for event in session.events()]

    assert events == [
        RealtimeEvent(kind="interim", text="你好", sentence_id=0),
        RealtimeEvent(kind="done"),
    ]


def _result_frame(text: str, *, slice_type: int, index: int = 0) -> dict[str, Any]:
    return {
        "code": 0,
        "result": {
            "slice_type": slice_type,
            "index": index,
            "voice_text_str": text,
            "start_time": 0,
            "end_time": 500,
        },
    }


def test_normalize_result_frames() -> None:
    """`16k_zh_en_2.0` answers with `result`, not the documented `sentences`."""
    interim = realtime.normalize_event(_result_frame("今天", slice_type=0))
    stable = realtime.normalize_event(_result_frame("今天天气不错", slice_type=1))
    ultimate = realtime.normalize_event(_result_frame("今天天气不错。", slice_type=2, index=1))

    assert interim == RealtimeEvent(kind="interim", text="今天", sentence_id=0)
    assert stable == RealtimeEvent(kind="final", text="今天天气不错", sentence_id=0)
    assert ultimate == RealtimeEvent(kind="final", text="今天天气不错。", sentence_id=1)


def test_normalize_sentences_frames() -> None:
    """The documented `sentences` shape is still accepted."""
    frame = {
        "code": 0,
        "sentences": {"sentence": "你好", "sentence_type": 1, "sentence_id": 3},
    }
    assert realtime.normalize_event(frame) == RealtimeEvent(
        kind="final", text="你好", sentence_id=3
    )


def test_normalize_terminal_and_error_frames() -> None:
    assert realtime.normalize_event({"code": 0, "final": 1}) == RealtimeEvent(kind="done")
    assert realtime.normalize_event({"code": 4004, "message": "exhausted"}) == RealtimeEvent(
        kind="error", error_code=4004
    )
    assert realtime.normalize_event({"code": 0, "result": {"slice_type": 1}}) is None


@pytest.mark.asyncio
async def test_close_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = FakeConnection([_handshake()])
    _patch_connect(monkeypatch, conn)

    session = realtime.open_session(CONFIG)
    await session.connect()
    await session.close()
    await session.close()

    assert conn.closed is True
    assert session.connected is False
