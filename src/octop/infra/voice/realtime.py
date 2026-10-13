"""Tencent Cloud realtime speech recognition (ASR V2) upstream session.

One :class:`TencentRealtimeSession` owns a single connection to
``wss://asr.cloud.tencent.com/asr/v2/<appid>``.  It is deliberately transport
agnostic: it pushes raw PCM frames upstream and yields the parsed JSON events
back, leaving the browser-facing WebSocket, localisation and error mapping to
the HTTP layer.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.tencent_asr_sign import DEFAULT_ENGINE, build_asr_v2_url

logger = logging.getLogger(__name__)

HANDSHAKE_TIMEOUT_SECONDS = 10.0
#: How long the router waits for ``final: 1`` after the client says "end".
READER_TIMEOUT_SECONDS = 15.0
CLOSE_TIMEOUT_SECONDS = 5.0
MAX_MESSAGE_BYTES = 1 << 20


@dataclass(frozen=True)
class RealtimeConfig:
    """Credentials needed to open one realtime ASR connection."""

    app_id: str
    secret_id: str
    secret_key: str
    engine: str = DEFAULT_ENGINE


@dataclass(frozen=True)
class RealtimeEvent:
    """One normalized upstream event.

    ``interim`` text is still being refined, ``final`` text replaces that
    sentence, ``done`` marks the end of the stream and ``error`` carries a
    Tencent error code.
    """

    kind: Literal["interim", "final", "done", "error"]
    text: str = ""
    sentence_id: int = 0
    error_code: int = 0


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def normalize_event(event: dict[str, Any]) -> RealtimeEvent | None:
    """Map a raw upstream frame onto a :class:`RealtimeEvent`.

    Tencent returns two shapes for the same stream: ``16k_zh_en_2.0`` sends
    ``result`` (``slice_type`` 0 = 中间结果, 1 = 稳定结果, 2 = 该句最终结果,
    ``index`` = sentence id, ``voice_text_str`` = text), while the API docs
    describe ``sentences``. Both are accepted.
    """
    code = _as_int(event.get("code"))
    if code != 0:
        return RealtimeEvent(kind="error", error_code=code)

    sentences = event.get("sentences")
    if isinstance(sentences, dict) and sentences.get("sentence"):
        return RealtimeEvent(
            kind="final" if _as_int(sentences.get("sentence_type")) == 1 else "interim",
            text=str(sentences["sentence"]),
            sentence_id=_as_int(sentences.get("sentence_id")),
        )

    result = event.get("result")
    if isinstance(result, dict) and result.get("voice_text_str"):
        return RealtimeEvent(
            kind="interim" if _as_int(result.get("slice_type")) == 0 else "final",
            text=str(result["voice_text_str"]),
            sentence_id=_as_int(result.get("index")),
        )

    if _as_int(event.get("final")) == 1:
        return RealtimeEvent(kind="done")
    return None


def _parse_control(raw: str | bytes) -> tuple[int, str] | None:
    """Return ``(code, message)`` of an upstream control frame, or ``None``."""
    try:
        data = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        code = int(data.get("code") or 0)
    except (TypeError, ValueError):
        code = 0
    return code, str(data.get("message") or "")


class TencentRealtimeSession:
    """A live realtime ASR stream for one browser session."""

    def __init__(self, config: RealtimeConfig) -> None:
        self._config = config
        self._ws: Any = None

    @property
    def connected(self) -> bool:
        return self._ws is not None

    async def connect(self) -> None:
        """Open the upstream connection and verify the handshake."""
        from websockets.asyncio.client import connect as ws_connect
        from websockets.exceptions import WebSocketException

        url = build_asr_v2_url(
            app_id=self._config.app_id,
            secret_id=self._config.secret_id,
            secret_key=self._config.secret_key,
            engine=self._config.engine,
        )
        try:
            self._ws = await ws_connect(
                url,
                # websockets >= 14 defaults to proxy=True, which silently routes
                # through HTTPS_PROXY / ALL_PROXY when the deployment sets one.
                proxy=None,
                # Tencent does not answer WebSocket pings; keepalive would abort.
                ping_interval=None,
                open_timeout=HANDSHAKE_TIMEOUT_SECONDS,
                close_timeout=CLOSE_TIMEOUT_SECONDS,
                max_size=MAX_MESSAGE_BYTES,
            )
            raw = await asyncio.wait_for(self._ws.recv(), timeout=HANDSHAKE_TIMEOUT_SECONDS)
        except (WebSocketException, OSError, TimeoutError) as exc:
            await self.close()
            raise OctopError(
                ErrorCode.VOICE_REALTIME_UNAVAILABLE,
                f"realtime ASR connect failed: {exc}",
            ) from exc

        control = _parse_control(raw)
        if control is None:
            await self.close()
            raise OctopError(
                ErrorCode.VOICE_REALTIME_UNAVAILABLE,
                "realtime ASR sent an unexpected handshake frame",
            )
        code, message = control
        if code != 0:
            await self.close()
            raise OctopError(
                ErrorCode.VOICE_REALTIME_UNAVAILABLE,
                f"realtime ASR handshake failed: {message or code}",
                details={"tencent_code": code},
            )

    async def send_audio(self, pcm: bytes) -> None:
        """Forward one PCM frame (16 kHz / 16-bit / mono) upstream."""
        if self._ws is None or not pcm:
            return
        await self._ws.send(pcm)

    async def finish(self) -> None:
        """Tell Tencent the audio stream ended so it can flush ``final``."""
        if self._ws is None:
            return
        await self._ws.send(json.dumps({"type": "end"}))

    async def events(self) -> AsyncIterator[RealtimeEvent]:
        """Yield normalized events until the connection closes."""
        from websockets.exceptions import ConnectionClosed

        if self._ws is None:
            return
        while True:
            try:
                raw = await self._ws.recv()
            except ConnectionClosed:
                return
            if isinstance(raw, (bytes, bytearray)):
                continue
            try:
                frame = json.loads(raw)
            except json.JSONDecodeError:
                logger.debug("realtime ASR sent a non-JSON text frame")
                continue
            if not isinstance(frame, dict):
                continue
            event = normalize_event(frame)
            if event is not None:
                yield event

    async def close(self) -> None:
        ws, self._ws = self._ws, None
        if ws is None:
            return
        try:
            await ws.close()
        except Exception:  # a failed close must not mask the real error
            logger.debug("realtime ASR close failed", exc_info=True)


def open_session(config: RealtimeConfig) -> TencentRealtimeSession:
    """Factory kept separate so tests can monkeypatch the upstream session."""
    return TencentRealtimeSession(config)
