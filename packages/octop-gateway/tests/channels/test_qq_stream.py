"""Unit tests for QQ C2C replace-mode streaming."""

from __future__ import annotations

import asyncio
import time
from itertools import pairwise
from typing import Any

import pytest

from octop_gateway.channels.qq import QQChannel, QQConfig
from octop_gateway.channels.qq.channel import (
    extract_think_blocks,
    strip_think_tags,
)
from octop_gateway.channels.qq.stream import (
    STREAM_DONE,
    STREAM_GENERATING,
    StreamFrame,
    StreamSession,
    next_stream_msg_seq,
    prefix_matches,
    reconcile_stream_text,
    reset_stream_msg_seq_for_tests,
)
from octop_gateway.models import (
    ChannelSubject,
    FileContent,
    InboundMessage,
    MessageEvent,
)


def _config(**overrides: object) -> QQConfig:
    data = {
        "app_id": "app",
        "secret": "secret",
        "c2c_streaming": True,
        "show_thinking": False,
        "show_tool_hints": False,
        "stream_throttle_ms": 0,
        "stream_hold_keepalive_s": 0,
        "stream_done_retries": 1,
    }
    data.update(overrides)
    return QQConfig.from_dict(data)


def _c2c_payload(text: str = "hello") -> dict[str, Any]:
    return {
        "t": "C2C_MESSAGE_CREATE",
        "d": {
            "id": "msg_in_1",
            "content": text,
            "author": {"user_openid": "user_open_1"},
        },
    }


def _group_payload(text: str = "hello") -> dict[str, Any]:
    return {
        "t": "GROUP_AT_MESSAGE_CREATE",
        "d": {
            "id": "msg_group_1",
            "content": text,
            "group_openid": "group_open_1",
            "author": {"member_openid": "member_1"},
        },
    }


class _FakeResp:
    def __init__(self, status: int = 200, body: str = '{"id":"stream-1"}') -> None:
        self.status = status
        self._body = body

    async def text(self) -> str:
        return self._body

    async def __aenter__(self) -> _FakeResp:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


class _FakeSession:
    def __init__(self) -> None:
        self.posts: list[dict[str, Any]] = []
        self.status = 200
        self.body = '{"id":"stream-1"}'

    def post(self, url: str, **kwargs: Any) -> _FakeResp:
        self.posts.append({"url": url, "json": kwargs.get("json"), "headers": kwargs.get("headers")})
        return _FakeResp(self.status, self.body)

    @property
    def closed(self) -> bool:
        return False


async def _delta_processor(_msg: InboundMessage):
    yield MessageEvent.delta("Hel")
    yield MessageEvent.delta("lo")
    yield MessageEvent.completed()


def _wire_http(channel: QQChannel) -> _FakeSession:
    session = _FakeSession()
    channel._http = session  # type: ignore[assignment]
    channel._access_token = "fake_token"
    channel._token_expires_at = time.time() + 3600
    channel._token_refresh_at = time.time() + 3600
    return session


def _stream_posts(http: _FakeSession) -> list[dict[str, Any]]:
    return [p for p in http.posts if str(p["url"]).endswith("/stream_messages")]


def _stream_texts(http: _FakeSession) -> list[str]:
    return [str(p["json"].get("content_raw") or "") for p in _stream_posts(http)]


def _static_texts(http: _FakeSession) -> list[str]:
    texts: list[str] = []
    for post in http.posts:
        if str(post["url"]).endswith("/stream_messages"):
            continue
        body = post.get("json") or {}
        if body.get("msg_type") == 6:
            continue
        markdown = body.get("markdown") or {}
        if isinstance(markdown, dict) and markdown.get("content"):
            texts.append(str(markdown["content"]))
        elif body.get("content"):
            texts.append(str(body["content"]))
    return texts


class TestThinkTags:
    def test_extract_and_strip_complete_block(self) -> None:
        raw = "<think>内部推理</think>下面是新闻"
        assert extract_think_blocks(raw) == "内部推理"
        assert strip_think_tags(raw) == "下面是新闻"

    def test_strip_closing_marker_without_open(self) -> None:
        assert strip_think_tags("hidden</think>可见回答") == "可见回答"

    def test_strip_unclosed_open(self) -> None:
        assert strip_think_tags("可见<think>还在想") == "可见"

    def test_strip_preserves_markdown_newlines(self) -> None:
        assert strip_think_tags("## 五\n\n") == "## 五\n\n"
        assert strip_think_tags("\n") == "\n"


class TestReconcile:
    def test_empty_accepted_uses_incoming(self) -> None:
        assert reconcile_stream_text("", "Hi") == "Hi"

    def test_prefix_continues(self) -> None:
        assert reconcile_stream_text("Hel", "Hello") == "Hello"

    def test_shorter_incoming_keeps_accepted(self) -> None:
        assert reconcile_stream_text("Hello", "Hel") == "Hello"

    def test_diverged_keeps_accepted_plus_new_tail(self) -> None:
        assert reconcile_stream_text("abc", "xy") == "abcxy"

    def test_newline_hold_is_kept_when_answer_arrives(self) -> None:
        assert prefix_matches("\n", "hello") is False
        assert reconcile_stream_text("\n", "hello") == "\nhello"
        assert reconcile_stream_text("\nHello", "Hello") == "\nHello"


class TestStreamSession:
    @pytest.mark.asyncio
    async def test_drain_sends_latest_full_text_then_done(self) -> None:
        frames: list[StreamFrame] = []

        async def send(frame: StreamFrame) -> str:
            frames.append(frame)
            return "sid-1"

        session = StreamSession(
            user_id="u1",
            msg_id="m1",
            msg_seq=7,
            throttle_ms=0,
            done_retries=1,
            send_frame=send,
        )
        session.offer("Hel")
        session.offer("Hello")
        await asyncio.sleep(0)
        await session.finish("Hello")

        generating = [f for f in frames if f.state == STREAM_GENERATING]
        assert generating
        assert generating[-1].text == "Hello"
        assert generating[-1].msg_seq == 7
        assert frames[-1].state == STREAM_DONE
        assert frames[-1].text == "Hello"
        assert session.stream_msg_id == "sid-1"
        assert session.index == len(frames)

    @pytest.mark.asyncio
    async def test_throttle_coalesces_pending_into_one_frame(self) -> None:
        frames: list[StreamFrame] = []
        clock = {"now": 0.0}

        async def send(frame: StreamFrame) -> str | None:
            frames.append(frame)
            return "sid"

        async def sleep(delay: float) -> None:
            clock["now"] += delay

        session = StreamSession(
            user_id="u1",
            msg_id="m1",
            msg_seq=1,
            throttle_ms=400,
            done_retries=1,
            send_frame=send,
            sleep=sleep,
            monotonic=lambda: clock["now"],
        )
        session.offer("A")
        await asyncio.sleep(0)
        session.offer("AB")
        session.offer("ABC")
        await asyncio.sleep(0)
        await session.finish("ABC")

        generating = [f for f in frames if f.state == STREAM_GENERATING]
        assert len(generating) >= 1
        assert generating[-1].text == "ABC"
        assert all(f.msg_seq == 1 for f in frames)

    @pytest.mark.asyncio
    async def test_failed_generating_frame_stops_drain(self) -> None:
        async def send(_frame: StreamFrame) -> str | None:
            raise RuntimeError("40034021")

        session = StreamSession(
            user_id="u1",
            msg_id="m1",
            throttle_ms=0,
            done_retries=1,
            send_frame=send,
        )
        session.offer("Hello")
        await asyncio.sleep(0)
        await session.finish("Hello")
        assert session.failed is True
        assert session.sent_frames == 0

    @pytest.mark.asyncio
    async def test_closing_drops_pending_before_done(self) -> None:
        frames: list[StreamFrame] = []
        gate = asyncio.Event()

        async def send(frame: StreamFrame) -> str | None:
            frames.append(frame)
            if frame.state == STREAM_GENERATING:
                await gate.wait()
            return "sid"

        session = StreamSession(
            user_id="u1",
            msg_id="m1",
            throttle_ms=0,
            done_retries=1,
            send_frame=send,
        )
        session.offer("one")
        await asyncio.sleep(0)
        session.offer("two")
        finish = asyncio.create_task(session.finish("one", discard_pending=True))
        await asyncio.sleep(0)
        assert session.closing is True
        assert session.pending is None
        gate.set()
        await finish
        assert frames[-1].state == STREAM_DONE
        assert frames[-1].text == "one"

    def test_stream_msg_seq_wraps(self) -> None:
        reset_stream_msg_seq_for_tests()
        first = next_stream_msg_seq()
        assert first == 1
        reset_stream_msg_seq_for_tests()

    @pytest.mark.asyncio
    async def test_offer_during_in_flight_hold_keeps_newline_prefix(self) -> None:
        frames: list[StreamFrame] = []
        gate = asyncio.Event()

        async def send(frame: StreamFrame) -> str:
            frames.append(frame)
            if frame.text == "\n":
                await gate.wait()
            return "sid"

        session = StreamSession(
            user_id="u1",
            msg_id="m1",
            msg_seq=1,
            throttle_ms=0,
            done_retries=1,
            send_frame=send,
        )
        session.offer("\n")
        await asyncio.sleep(0)
        session.offer("Hello")
        gate.set()
        await session.finish("\nHello")
        generating = [f.text for f in frames if f.state == STREAM_GENERATING]
        assert generating[0] == "\n"
        assert generating[-1] == "\nHello"
        assert frames[-1].text == "\nHello"


class TestQQChannelStream:
    @pytest.mark.asyncio
    async def test_switch_off_uses_origin_main_static_markdown(self) -> None:
        raw = "导语\n\n##🌐标题\n- 条目\n**说明**"

        async def processor(_msg: InboundMessage):
            yield MessageEvent.delta(raw)
            yield MessageEvent.completed()

        ch = QQChannel(processor=processor, config=_config(c2c_streaming=False))
        http = _wire_http(ch)
        await ch.handle_inbound(_c2c_payload())
        assert _static_texts(http) == [raw]
        assert not _stream_posts(http)

    def test_legacy_streaming_flag_does_not_control_c2c(self) -> None:
        config = QQConfig.from_dict({"app_id": "a", "secret": "s", "streaming": False, "response_mode": "invoke"})
        assert config.c2c_streaming is True

    @pytest.mark.asyncio
    async def test_switch_on_streams_raw_answer(self) -> None:
        ch = QQChannel(processor=_delta_processor, config=_config())
        http = _wire_http(ch)
        await ch.handle_inbound(_c2c_payload())
        assert _stream_posts(http)
        generating = [
            str(p["json"].get("content_raw") or "")
            for p in _stream_posts(http)
            if p["json"].get("input_state") == STREAM_GENERATING
        ]
        assert generating
        assert all(frame.strip() for frame in generating)
        assert _stream_texts(http)[-1].strip() == "Hello"
        assert _stream_posts(http)[-1]["json"]["input_state"] == STREAM_DONE
        assert {p["json"]["content_type"] for p in _stream_posts(http)} == {"markdown"}
        assert not _static_texts(http)
        assert not any((p.get("json") or {}).get("msg_type") == 6 for p in http.posts)

    @pytest.mark.asyncio
    async def test_processor_starts_before_hold_http_returns(self) -> None:
        started = asyncio.Event()
        release_hold = asyncio.Event()

        class _GatedResp(_FakeResp):
            async def __aenter__(self) -> _FakeResp:
                await release_hold.wait()
                return self

        class _SlowHold(_FakeSession):
            def post(self, url: str, **kwargs: Any) -> _FakeResp:
                body = kwargs.get("json") or {}
                self.posts.append({"url": url, "json": body, "headers": kwargs.get("headers")})
                if str(url).endswith("/stream_messages") and str(body.get("content_raw") or "") == "\n":
                    return _GatedResp(self.status, self.body)
                return _FakeResp(self.status, self.body)

        async def processor(_msg: InboundMessage):
            started.set()
            yield MessageEvent.delta("Hello")
            yield MessageEvent.completed()

        ch = QQChannel(processor=processor, config=_config())
        http = _SlowHold()
        ch._http = http  # type: ignore[assignment]
        ch._access_token = "fake_token"
        ch._token_expires_at = time.time() + 3600
        ch._token_refresh_at = time.time() + 3600
        task = asyncio.create_task(ch.handle_inbound(_c2c_payload()))
        await asyncio.wait_for(started.wait(), timeout=1.0)
        release_hold.set()
        await task
        assert _stream_texts(http)[-1].strip() == "Hello"
        assert all(text.strip() for text in _stream_texts(http))

    @pytest.mark.asyncio
    async def test_group_does_not_use_stream_messages(self) -> None:
        sent: list[str] = []

        async def processor(_msg: InboundMessage):
            yield MessageEvent.delta("Hello")
            yield MessageEvent.completed()

        ch = QQChannel(processor=processor, config=_config())
        http = _wire_http(ch)

        async def capture(_subject: ChannelSubject, text: str) -> None:
            sent.append(text)

        ch._send_text = capture  # type: ignore[method-assign]
        await ch.handle_inbound(_group_payload())
        assert sent == ["Hello"]
        assert not any(str(p["url"]).endswith("/stream_messages") for p in http.posts)

    @pytest.mark.asyncio
    async def test_stream_failure_falls_back_to_static(self) -> None:
        sent: list[str] = []

        ch = QQChannel(processor=_delta_processor, config=_config())
        http = _wire_http(ch)
        http.status = 400
        http.body = '{"code":40034021}'

        async def capture(_subject: ChannelSubject, text: str) -> None:
            sent.append(text)

        ch._send_text = capture  # type: ignore[method-assign]
        await ch.handle_inbound(_c2c_payload())
        assert sent == ["Hello"]

    @pytest.mark.asyncio
    async def test_http_200_with_qq_error_code_falls_back_to_static(self) -> None:
        sent: list[str] = []

        ch = QQChannel(processor=_delta_processor, config=_config())
        http = _wire_http(ch)
        http.status = 200
        http.body = '{"code":40007,"message":"已下发内容前缀不可修改"}'

        async def capture(_subject: ChannelSubject, text: str) -> None:
            sent.append(text)

        ch._send_text = capture  # type: ignore[method-assign]
        await ch.handle_inbound(_c2c_payload())
        assert sent == ["Hello"]

    @pytest.mark.asyncio
    async def test_hold_only_failure_falls_back_to_static(self) -> None:
        sent: list[str] = []

        class _HoldThenFail(_FakeSession):
            def post(self, url: str, **kwargs: Any) -> _FakeResp:
                body = kwargs.get("json") or {}
                self.posts.append({"url": url, "json": body, "headers": kwargs.get("headers")})
                if str(url).endswith("/stream_messages"):
                    raw = str(body.get("content_raw") or "")
                    if raw.strip() == "" and body.get("input_state") == STREAM_GENERATING:
                        return _FakeResp(200, '{"id":"stream-1"}')
                    return _FakeResp(
                        200,
                        '{"code":40007,"message":"已下发内容前缀不可修改"}',
                    )
                return _FakeResp(200, '{"id":"ok"}')

        async def processor(_msg: InboundMessage):
            await asyncio.sleep(0.05)
            yield MessageEvent.delta("Hello")
            yield MessageEvent.completed()

        ch = QQChannel(processor=processor, config=_config())
        http = _HoldThenFail()
        ch._http = http  # type: ignore[assignment]
        ch._access_token = "fake_token"
        ch._token_expires_at = time.time() + 3600
        ch._token_refresh_at = time.time() + 3600

        async def capture(_subject: ChannelSubject, text: str) -> None:
            sent.append(text)

        ch._send_text = capture  # type: ignore[method-assign]
        await ch.handle_inbound(_c2c_payload())
        assert sent == ["Hello"]
        assert _stream_posts(http)
        assert all(str(p["json"].get("content_raw") or "").strip() for p in _stream_posts(http))

    @pytest.mark.asyncio
    async def test_one_rate_slot_for_the_text_stream(self) -> None:
        counter = 0

        async def counting() -> None:
            nonlocal counter
            counter += 1

        ch = QQChannel(processor=_delta_processor, config=_config())
        _wire_http(ch)
        ch._acquire_rate_slot = counting  # type: ignore[method-assign]
        await ch.handle_inbound(_c2c_payload())
        assert counter == 1

    @pytest.mark.asyncio
    async def test_message_media_is_sent_after_done(self) -> None:
        from octop_gateway.models import MessageEventType

        media_sent: list[object] = []

        async def processor_media(_msg: InboundMessage):
            yield MessageEvent.delta("see file")
            yield MessageEvent(
                type=MessageEventType.MESSAGE,
                content=[FileContent(filename="a.pdf", local_path="a.pdf")],
            )
            yield MessageEvent.completed()

        ch = QQChannel(processor=processor_media, config=_config())
        http = _wire_http(ch)

        async def capture_media(_subject: ChannelSubject, media: object) -> None:
            media_sent.append(media)

        ch.reply_media = capture_media  # type: ignore[method-assign]
        await ch.handle_inbound(_c2c_payload())
        assert media_sent
        assert "see file" in _stream_texts(http)[-1]

    def test_config_streaming_defaults(self) -> None:
        config = QQConfig.from_dict({"app_id": "a", "secret": "s"})
        assert config.c2c_streaming is True
        assert config.stream_throttle_ms == 150
        assert config.stream_hold_keepalive_s == 3.0
        config_off = QQConfig.from_dict({"app_id": "a", "secret": "s", "c2c_streaming": False})
        assert config_off.c2c_streaming is False
        config_str = QQConfig.from_dict({"app_id": "a", "secret": "s", "c2c_streaming": "false"})
        assert config_str.c2c_streaming is False

    @pytest.mark.asyncio
    async def test_tool_narration_is_omitted_from_answer(self) -> None:
        async def processor(_msg: InboundMessage):
            yield MessageEvent.delta("Let me search. ")
            yield MessageEvent.tool_start("search")
            yield MessageEvent.tool_end("search")
            yield MessageEvent.delta("下面是新闻")
            yield MessageEvent.completed()

        ch = QQChannel(processor=processor, config=_config())
        http = _wire_http(ch)
        await ch.handle_inbound(_c2c_payload())
        assert _stream_texts(http)
        assert all(text.strip() for text in _stream_texts(http))
        assert _stream_texts(http)[-1].strip() == "下面是新闻"
        assert all("Let me search" not in text for text in _stream_texts(http))
        assert not _static_texts(http)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("in_flight", [False, True], ids=["accepted", "in-flight"])
    async def test_answer_after_visible_tool_narration_is_not_repeated(self, in_flight: bool) -> None:
        narration = "正在开票。\n\n"
        answer_parts = ["## 开票完成\n\n", "### 抬头 / 主体\n\n", "- 主体：测试公司\n", "- 票种：普通发票\n"]
        narration_started = asyncio.Event()
        release_narration = asyncio.Event()

        class _NarrationResp(_FakeResp):
            async def text(self) -> str:
                narration_started.set()
                if in_flight:
                    await release_narration.wait()
                return await super().text()

        class _NarrationSession(_FakeSession):
            def post(self, url: str, **kwargs: Any) -> _FakeResp:
                response = super().post(url, **kwargs)
                if (kwargs.get("json") or {}).get("content_raw") == narration:
                    return _NarrationResp()
                return response

        async def processor(_msg: InboundMessage):
            yield MessageEvent.delta(narration)
            await narration_started.wait()
            yield MessageEvent.tool_start("invoice")
            yield MessageEvent.tool_end("invoice")
            for part in answer_parts:
                yield MessageEvent.delta(part)
                await asyncio.sleep(0)
            release_narration.set()
            yield MessageEvent.completed()

        ch = QQChannel(processor=processor, config=_config())
        http = _NarrationSession()
        ch._http = http  # type: ignore[assignment]
        ch._access_token = "fake_token"
        ch._token_expires_at = time.time() + 3600
        ch._token_refresh_at = time.time() + 3600
        await asyncio.wait_for(ch.handle_inbound(_c2c_payload()), timeout=1.0)

        texts = _stream_texts(http)
        assert texts[-1] == narration + "".join(answer_parts)
        assert all(text.count("## 开票完成") <= 1 for text in texts)
        assert all(text.count("### 抬头 / 主体") <= 1 for text in texts)
        assert all(current.startswith(previous) for previous, current in pairwise(texts))
        assert not _static_texts(http)

    @pytest.mark.asyncio
    async def test_wait_shows_typing_instead_of_a_blank_bubble(self) -> None:
        async def processor(_msg: InboundMessage):
            await asyncio.sleep(0.12)
            yield MessageEvent.delta("下面是新闻")
            yield MessageEvent.completed()

        ch = QQChannel(processor=processor, config=_config(stream_hold_keepalive_s=0.04))
        http = _wire_http(ch)
        await ch.handle_inbound(_c2c_payload())
        typing = [p for p in http.posts if (p.get("json") or {}).get("msg_type") == 6]
        assert len(typing) >= 2
        assert all(str(p["json"].get("content_raw") or "").strip() for p in _stream_posts(http))
        assert _stream_texts(http)[-1].strip() == "下面是新闻"

    @pytest.mark.asyncio
    async def test_incomplete_table_is_not_streamed_until_first_row(self) -> None:
        async def processor(_msg: InboundMessage):
            yield MessageEvent.delta("## 五\n\n")
            await asyncio.sleep(0)
            yield MessageEvent.delta("| 能力 | 说明 |\n")
            await asyncio.sleep(0)
            yield MessageEvent.delta("| --- | --- |\n")
            await asyncio.sleep(0)
            yield MessageEvent.delta("| 意图路由 | 分派流程 |\n")
            await asyncio.sleep(0)
            yield MessageEvent.delta("| 问答还在写")
            await asyncio.sleep(0)
            yield MessageEvent.completed()

        ch = QQChannel(processor=processor, config=_config())
        http = _wire_http(ch)
        await ch.handle_inbound(_c2c_payload())
        generating = [
            str(p["json"].get("content_raw") or "")
            for p in _stream_posts(http)
            if p["json"].get("input_state") == STREAM_GENERATING
        ]
        visible = [frame for frame in generating if frame.strip()]
        assert generating
        assert all(frame.strip() for frame in generating)
        assert visible
        assert visible[0].strip() == "## 五"
        assert all("| 能力 |" not in frame or "| 意图路由 |" in frame for frame in generating)
        assert any("| 意图路由 | 分派流程 |" in frame and "| 问答还在写" not in frame for frame in generating)
        assert "| 问答还在写" in _stream_texts(http)[-1]

    @pytest.mark.asyncio
    async def test_think_tags_stay_out_of_streamed_answer(self) -> None:
        async def processor(_msg: InboundMessage):
            yield MessageEvent.delta("<think>内部推理</think>下面是新闻")
            yield MessageEvent.completed()

        ch = QQChannel(processor=processor, config=_config())
        http = _wire_http(ch)
        await ch.handle_inbound(_c2c_payload())
        assert all(text.strip() for text in _stream_texts(http))
        assert _stream_texts(http)[-1].strip() == "下面是新闻"
        assert all("内部推理" not in text for text in _stream_texts(http))


class TestStreamDoesNotRepeat:
    @pytest.mark.asyncio
    async def test_identical_prefix_is_replaced_not_repeated(self) -> None:
        """A stable table prefix must not be posted again on every token."""

        async def processor(_msg: InboundMessage):
            yield MessageEvent.delta("导语。\n\n| 指数 | 收盘 |\n| --- | --- |\n| 上证 | 3888 |\n")
            for _ in range(30):
                yield MessageEvent.delta("深")
                await asyncio.sleep(0)
            yield MessageEvent.delta("证 | 13316 |\n")
            for _ in range(20):
                yield MessageEvent.delta("还")
                await asyncio.sleep(0)
            yield MessageEvent.completed()

        ch = QQChannel(processor=processor, config=_config())
        http = _wire_http(ch)
        await ch.handle_inbound(_c2c_payload())

        generating = [
            str(p["json"].get("content_raw") or "")
            for p in _stream_posts(http)
            if p["json"].get("input_state") == STREAM_GENERATING and str(p["json"].get("content_raw") or "").strip()
        ]
        assert len(generating) == len(set(generating))
        assert len(generating) <= 3
        assert sum("深证 | 13316 |" not in frame for frame in generating) == 1
        assert any("深证 | 13316 |" in frame for frame in generating)
        linked = [p["json"] for p in _stream_posts(http) if p["json"].get("stream_msg_id")]
        assert linked
        assert {body["stream_msg_id"] for body in linked} == {"stream-1"}
        assert _stream_posts(http)[-1]["json"]["input_state"] == STREAM_DONE
        assert not _static_texts(http)

    @pytest.mark.asyncio
    async def test_nested_stream_id_stays_on_one_chain(self) -> None:
        ch = QQChannel(processor=_delta_processor, config=_config())
        http = _wire_http(ch)
        http.body = '{"code":0,"data":{"id":99}}'
        await ch.handle_inbound(_c2c_payload())
        assert not _static_texts(http)
        assert _stream_texts(http)[-1].strip() == "Hello"
        assert _stream_posts(http)[-1]["json"]["stream_msg_id"] == "99"

    @pytest.mark.asyncio
    async def test_missing_stream_id_sends_the_answer_once(self) -> None:
        sent: list[str] = []

        async def processor(_msg: InboundMessage):
            yield MessageEvent.delta("导语。\n\n| 指数 | 收盘 |\n| --- | --- |\n| 上证 | 3888 |\n")
            for _ in range(25):
                yield MessageEvent.delta("深证还在写")
                await asyncio.sleep(0)
            yield MessageEvent.completed()

        ch = QQChannel(processor=processor, config=_config())
        http = _wire_http(ch)
        http.body = '{"code":0}'

        async def capture(_subject: ChannelSubject, text: str) -> None:
            sent.append(text)

        ch._send_text = capture  # type: ignore[method-assign]
        await ch.handle_inbound(_c2c_payload())

        visible = [
            str(p["json"].get("content_raw") or "")
            for p in _stream_posts(http)
            if str(p["json"].get("content_raw") or "").strip()
        ]
        assert len(visible) == 1
        assert "上证 | 3888 |" in visible[0]
        assert "深证还在写" not in visible[0]
        assert all(p["json"].get("input_state") != STREAM_DONE for p in _stream_posts(http))
        assert sent == ["导语。\n\n| 指数 | 收盘 |\n| --- | --- |\n| 上证 | 3888 |\n" + "深证还在写" * 25]
