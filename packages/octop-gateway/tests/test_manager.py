"""Tests for octop_gateway.manager (ChannelManager)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import pytest

from octop_gateway.channel import BaseChannel, ChannelConfig, MessageProcessor
from octop_gateway.manager import ChannelManager
from octop_gateway.models import (
    ChannelSubject,
    ContentPart,
    InboundMessage,
    MessageEvent,
    TextContent,
)

# --- Test channel ---


class MockChannel(BaseChannel):
    """Mock channel for testing ChannelManager."""

    channel_type = "mock"

    def __init__(self, processor: MessageProcessor) -> None:
        super().__init__(processor)
        self.sent: list[tuple[str, str]] = []
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def _send_text(self, subject: ChannelSubject, text: str) -> None:
        self.sent.append((subject.subject_id, text))

    async def _send_content(self, subject: ChannelSubject, parts: list[ContentPart]) -> None:
        for p in parts:
            if isinstance(p, TextContent):
                self.sent.append((subject.subject_id, p.text))

    async def _send_media(self, subject: ChannelSubject, media: ContentPart) -> None:
        pass

    def parse_inbound(self, raw_payload: Any) -> InboundMessage:
        if isinstance(raw_payload, InboundMessage):
            return raw_payload
        text = raw_payload if isinstance(raw_payload, str) else str(raw_payload)
        return InboundMessage(
            channel_id=self.channel_id,
            channel_type=self.channel_type,
            content=[TextContent(text=text)],
            channel_subject=ChannelSubject(subject_id="user1"),
        )


def _make_user(user_id: str) -> ChannelSubject:
    """Create a minimal ChannelSubject for testing push methods."""
    now = time.time()
    return ChannelSubject(
        subject_id=user_id,
        first_seen=now,
        last_seen=now,
    )


async def _echo_processor(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
    """Simple test processor."""
    yield MessageEvent.text(f"Reply: {msg.text}")
    yield MessageEvent.completed()


# --- Tests ---


class TestChannelManager:
    """Test ChannelManager orchestration."""

    @pytest.mark.asyncio
    async def test_start_stop(self) -> None:
        ch = MockChannel(processor=_echo_processor)
        mgr = ChannelManager({ch.channel_id: ch}, workers_per_channel=1)

        await mgr.start()
        assert ch.started

        await mgr.stop()
        assert ch.stopped

    @pytest.mark.asyncio
    async def test_channel_ids(self) -> None:
        ch = MockChannel(processor=_echo_processor)
        mgr = ChannelManager({ch.channel_id: ch})
        assert ch.channel_id in mgr.channel_ids

    @pytest.mark.asyncio
    async def test_get_channel(self) -> None:
        ch = MockChannel(processor=_echo_processor)
        mgr = ChannelManager({ch.channel_id: ch})
        assert mgr.get_channel(ch.channel_id) is ch
        assert mgr.get_channel("nonexistent") is None

    @pytest.mark.asyncio
    async def test_run_in_session_waits_for_inbound_turn(self) -> None:
        inbound_started = asyncio.Event()
        release_inbound = asyncio.Event()
        operation_started = asyncio.Event()

        async def blocking_processor(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
            inbound_started.set()
            await release_inbound.wait()
            yield MessageEvent.completed()

        async def operation() -> str:
            operation_started.set()
            return "done"

        ch = MockChannel(processor=blocking_processor)
        mgr = ChannelManager({ch.channel_id: ch}, workers_per_channel=1)
        await mgr.start()
        try:
            mgr.enqueue(ch.channel_id, "hello")
            await asyncio.wait_for(inbound_started.wait(), timeout=1)
            task = asyncio.create_task(mgr.run_in_session(ch.channel_id, "user1", operation))
            await asyncio.sleep(0)
            assert not operation_started.is_set()

            release_inbound.set()
            assert await asyncio.wait_for(task, timeout=1) == "done"
            assert operation_started.is_set()
        finally:
            await mgr.stop()

    @pytest.mark.asyncio
    async def test_run_in_session_validates_channel_and_key(self) -> None:
        ch = MockChannel(processor=_echo_processor)
        mgr = ChannelManager({ch.channel_id: ch})

        async def operation() -> None:
            return None

        with pytest.raises(ValueError, match="Channel not found"):
            await mgr.run_in_session("missing", "user1", operation)
        with pytest.raises(ValueError, match="session_key"):
            await mgr.run_in_session(ch.channel_id, " ", operation)

    @pytest.mark.asyncio
    async def test_enqueue_and_process(self) -> None:
        ch = MockChannel(processor=_echo_processor)
        mgr = ChannelManager({ch.channel_id: ch}, workers_per_channel=1)
        await mgr.start()

        try:
            mgr.enqueue(ch.channel_id, "hello")
            # Give worker time to process
            await asyncio.sleep(0.2)
            assert len(ch.sent) >= 1
            assert any("Reply: hello" in msg for _, msg in ch.sent)
        finally:
            await mgr.stop()

    @pytest.mark.asyncio
    async def test_pre_lock_handler_runs_before_processing(self) -> None:
        seen: list[str] = []

        async def on_pre_lock(channel_id: str, message: InboundMessage) -> None:
            seen.append(f"{channel_id}:{message.text}")

        ch = MockChannel(processor=_echo_processor)
        mgr = ChannelManager(
            {ch.channel_id: ch},
            workers_per_channel=1,
            on_pre_lock=on_pre_lock,
        )
        await mgr.start()
        try:
            mgr.enqueue(ch.channel_id, "/stop")
            await asyncio.sleep(0.2)
            assert seen == [f"{ch.channel_id}:/stop"]
            assert any("Reply: /stop" in msg for _, msg in ch.sent)
        finally:
            await mgr.stop()

    @pytest.mark.asyncio
    async def test_control_messages_are_not_merged_with_regular_messages(self) -> None:
        seen: list[str] = []

        async def capture(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
            seen.append(msg.text)
            yield MessageEvent.completed()

        ch = MockChannel(processor=capture)
        mgr = ChannelManager(
            {ch.channel_id: ch},
            workers_per_channel=1,
            control_message_predicate=lambda msg: msg.text.lstrip().startswith("/"),
        )
        await mgr.start()
        try:
            queue = mgr._queues[ch.channel_id]
            queue.put_nowait("hello")
            queue.put_nowait("/new")
            for _ in range(50):
                if len(seen) == 2:
                    break
                await asyncio.sleep(0.01)
            assert seen == ["hello", "/new"]
        finally:
            await mgr.stop()

    @pytest.mark.asyncio
    async def test_regular_messages_still_batch_when_control_predicate_is_configured(self) -> None:
        seen: list[str] = []

        async def capture(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
            seen.append(msg.text)
            yield MessageEvent.completed()

        ch = MockChannel(processor=capture)
        mgr = ChannelManager(
            {ch.channel_id: ch},
            workers_per_channel=1,
            control_message_predicate=lambda msg: msg.text.lstrip().startswith("/"),
        )
        await mgr.start()
        try:
            queue = mgr._queues[ch.channel_id]
            queue.put_nowait("hello")
            queue.put_nowait("world")
            for _ in range(50):
                if seen:
                    break
                await asyncio.sleep(0.01)
            assert seen == ["hello\nworld"]
        finally:
            await mgr.stop()

    @pytest.mark.asyncio
    async def test_interrupt_message_bypasses_busy_session_worker(self) -> None:
        work_started = asyncio.Event()
        release_work = asyncio.Event()
        stop_seen = asyncio.Event()

        async def blocking_processor(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
            if msg.text == "work":
                work_started.set()
                await release_work.wait()
            elif msg.text == "/stop":
                stop_seen.set()
            yield MessageEvent.completed()

        ch = MockChannel(processor=blocking_processor)
        mgr = ChannelManager(
            {ch.channel_id: ch},
            workers_per_channel=1,
            control_message_predicate=lambda msg: msg.text.lstrip().startswith("/"),
            interrupt_message_predicate=lambda msg: msg.text.strip() == "/stop",
        )
        await mgr.start()
        try:
            mgr.enqueue(ch.channel_id, "work")
            await asyncio.wait_for(work_started.wait(), timeout=1)
            mgr.enqueue(ch.channel_id, "/stop")
            await asyncio.wait_for(stop_seen.wait(), timeout=1)
            assert not release_work.is_set()
        finally:
            release_work.set()
            await mgr.stop()

    @pytest.mark.asyncio
    async def test_push_text(self) -> None:
        ch = MockChannel(processor=_echo_processor)
        mgr = ChannelManager({ch.channel_id: ch}, workers_per_channel=1)
        await mgr.start()

        try:
            await mgr.push_text(ch.channel_id, _make_user("user1"), "pushed message")
            assert ("user1", "pushed message") in ch.sent
        finally:
            await mgr.stop()

    @pytest.mark.asyncio
    async def test_push_content(self) -> None:
        ch = MockChannel(processor=_echo_processor)
        mgr = ChannelManager({ch.channel_id: ch}, workers_per_channel=1)
        await mgr.start()

        try:
            await mgr.push_content(ch.channel_id, _make_user("user1"), [TextContent(text="content push")])
            assert ("user1", "content push") in ch.sent
        finally:
            await mgr.stop()

    @pytest.mark.asyncio
    async def test_push_nonexistent_channel_raises(self) -> None:
        mgr = ChannelManager({})
        with pytest.raises(ValueError, match="Channel not found"):
            await mgr.push_text("nonexistent", _make_user("user1"), "text")

    @pytest.mark.asyncio
    async def test_add_channel(self) -> None:
        mgr = ChannelManager({}, workers_per_channel=1)
        await mgr.start()

        try:
            ch = MockChannel(processor=_echo_processor)
            returned_id = await mgr.add_channel(ch)
            assert returned_id == ch.channel_id
            assert ch.channel_id in mgr.channel_ids
            assert ch.started
        finally:
            await mgr.stop()

    @pytest.mark.asyncio
    async def test_add_duplicate_raises(self) -> None:
        ch = MockChannel(processor=_echo_processor)
        mgr = ChannelManager({ch.channel_id: ch}, workers_per_channel=1)
        await mgr.start()

        try:
            # Creating another MockChannel with same channel_id
            ch2 = MockChannel.__new__(MockChannel)
            BaseChannel.__init__(ch2, _echo_processor, channel_id=ch.channel_id)
            ch2.sent = []
            ch2.started = False
            ch2.stopped = False
            with pytest.raises(ValueError, match="already exists"):
                await mgr.add_channel(ch2)
        finally:
            await mgr.stop()

    @pytest.mark.asyncio
    async def test_remove_channel(self) -> None:
        ch = MockChannel(processor=_echo_processor)
        mgr = ChannelManager({ch.channel_id: ch}, workers_per_channel=1)
        await mgr.start()

        try:
            await mgr.remove_channel(ch.channel_id)
            assert ch.channel_id not in mgr.channel_ids
            assert ch.stopped
        finally:
            await mgr.stop()

    @pytest.mark.asyncio
    async def test_enqueue_thread_safe(self) -> None:
        """enqueue() called from another thread should still deliver to workers."""
        import threading

        ch = MockChannel(processor=_echo_processor)
        mgr = ChannelManager({ch.channel_id: ch}, workers_per_channel=1)
        await mgr.start()

        try:
            # Call enqueue from a background thread
            def enqueue_from_thread():
                mgr.enqueue(ch.channel_id, "from-thread")

            t = threading.Thread(target=enqueue_from_thread)
            t.start()
            t.join(timeout=2)

            # Give worker time to process
            await asyncio.sleep(0.5)
            assert any("Reply: from-thread" in msg for _, msg in ch.sent)
        finally:
            await mgr.stop()

    @pytest.mark.asyncio
    async def test_enqueue_nonexistent_channel_drops(self) -> None:
        """enqueue() with unknown channel_id should not crash."""
        mgr = ChannelManager({}, workers_per_channel=1)
        await mgr.start()
        try:
            # Should not raise
            mgr.enqueue("nonexistent", "payload")
        finally:
            await mgr.stop()

    @pytest.mark.asyncio
    async def test_media_backend_propagated_to_channels(self, tmp_path) -> None:
        """Manager with media_backend should propagate it to all channels on start."""
        from octop_gateway.media import FileSystemMediaBackend

        backend = FileSystemMediaBackend(tmp_path)
        ch = MockChannel(processor=_echo_processor)
        mgr = ChannelManager({ch.channel_id: ch}, workers_per_channel=1, media_backend=backend)

        await mgr.start()
        try:
            assert ch._media_backend is backend
        finally:
            await mgr.stop()

    @pytest.mark.asyncio
    async def test_no_backend_uses_default_filesystem(self) -> None:
        """Manager without media_backend should default to FileSystemMediaBackend("/")."""
        from octop_gateway.media import FileSystemMediaBackend

        ch = MockChannel(processor=_echo_processor)
        mgr = ChannelManager({ch.channel_id: ch}, workers_per_channel=1)

        await mgr.start()
        try:
            assert isinstance(ch._media_backend, FileSystemMediaBackend)
            assert ch._media_backend.root_path.as_posix() == "/"
        finally:
            await mgr.stop()

    @pytest.mark.asyncio
    async def test_media_backend_propagated_on_add_channel(self, tmp_path) -> None:
        """add_channel() should propagate media_backend to the new channel."""
        from octop_gateway.media import FileSystemMediaBackend

        backend = FileSystemMediaBackend(tmp_path)
        mgr = ChannelManager({}, workers_per_channel=1, media_backend=backend)
        await mgr.start()

        try:
            ch = MockChannel(processor=_echo_processor)
            await mgr.add_channel(ch)
            assert ch._media_backend is backend
        finally:
            await mgr.stop()


# ---------------------------------------------------------------------------
# ChannelConfig tests
# ---------------------------------------------------------------------------


class TestChannelConfig:
    """Tests for ChannelConfig base class."""

    def test_fields_present(self) -> None:
        from octop_gateway.channel import ChannelConfig

        cfg = ChannelConfig()
        assert cfg.channel_id is None
        assert cfg.tenant_id is None

    def test_explicit_values(self) -> None:
        from octop_gateway.channel import ChannelConfig

        cfg = ChannelConfig(channel_id="abc", tenant_id="acme")
        assert cfg.channel_id == "abc"
        assert cfg.tenant_id == "acme"

    def test_from_dict_basic(self) -> None:
        from octop_gateway.channel import ChannelConfig

        cfg = ChannelConfig.from_dict({"channel_id": "x", "tenant_id": "t"})
        assert cfg.channel_id == "x"
        assert cfg.tenant_id == "t"

    def test_from_dict_ignores_unknown(self) -> None:
        from octop_gateway.channel import ChannelConfig

        cfg = ChannelConfig.from_dict({"tenant_id": "t", "unknown_key": "ignored"})
        assert cfg.tenant_id == "t"

    def test_subclass_from_dict(self) -> None:
        """Subclass from_dict should include platform-specific fields."""
        from octop_gateway.channels.feishu import FeishuConfig

        cfg = FeishuConfig.from_dict(
            {
                "app_id": "cli_xxx",
                "app_secret": "yyy",
                "tenant_id": "acme",
                "unknown_key": "ignored",
            }
        )
        assert cfg.app_id == "cli_xxx"
        assert cfg.app_secret == "yyy"
        assert cfg.tenant_id == "acme"

    def test_channel_config_inherited_by_feishu(self) -> None:
        from octop_gateway.channel import ChannelConfig
        from octop_gateway.channels.feishu import FeishuConfig

        assert issubclass(FeishuConfig, ChannelConfig)

    def test_channel_config_inherited_by_wecom(self) -> None:
        from octop_gateway.channel import ChannelConfig
        from octop_gateway.channels.wecom import WeComConfig

        assert issubclass(WeComConfig, ChannelConfig)

    def test_channel_config_inherited_by_qq(self) -> None:
        from octop_gateway.channel import ChannelConfig
        from octop_gateway.channels.qq import QQConfig

        assert issubclass(QQConfig, ChannelConfig)


# ---------------------------------------------------------------------------
# Convenience add_*_channel method tests (using MockChannel via add_channel)
# ---------------------------------------------------------------------------


class MockConfigChannel(BaseChannel):
    """Mock channel that accepts a config object (like real channels do)."""

    channel_type = "mock_cfg"

    def __init__(
        self,
        processor,
        config=None,
        *,
        channel_id=None,
        tenant_id=None,
        **kwargs,
    ) -> None:
        super().__init__(processor, channel_id=channel_id, tenant_id=tenant_id)
        self.config = config
        self.sent: list[tuple[str, str]] = []

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def _send_text(self, subject: ChannelSubject, text) -> None:
        self.sent.append((subject.subject_id, text))

    async def _send_content(self, subject: ChannelSubject, parts) -> None:
        pass

    async def _send_media(self, subject: ChannelSubject, media) -> None:
        pass

    def parse_inbound(self, raw_payload: Any) -> Any:
        from octop_gateway.models import InboundMessage, TextContent

        return InboundMessage(
            channel_id=self.channel_id,
            channel_type=self.channel_type,
            tenant_id=self._tenant_id,
            content=[TextContent(text=str(raw_payload))],
            channel_subject=ChannelSubject(subject_id="u1"),
        )


class TestAddChannelConfig:
    """Test add_channel with ChannelConfig objects (tenant_id/channel_id inheritance)."""

    @pytest.mark.asyncio
    async def test_tenant_id_from_config_propagates_to_channel(self) -> None:
        """tenant_id set on ChannelConfig should reach the channel instance."""

        mgr = ChannelManager(processor=_echo_processor, workers_per_channel=1)
        await mgr.start()
        try:
            # Patch BUILTIN_CHANNELS to include our mock
            from octop_gateway.channels import BUILTIN_CHANNELS

            BUILTIN_CHANNELS["mock_cfg"] = MockConfigChannel

            @dataclass
            class MockCfg(ChannelConfig):
                pass

            ch_id = await mgr.add_channel("mock_cfg", MockCfg(tenant_id="acme"))
            channel = mgr.get_channel(ch_id)
            assert channel is not None
            assert channel.tenant_id == "acme"
        finally:
            await mgr.stop()
            BUILTIN_CHANNELS.pop("mock_cfg", None)

    @pytest.mark.asyncio
    async def test_channel_id_from_config_used_as_key(self) -> None:
        """channel_id set on ChannelConfig should be used as the registration key."""
        from octop_gateway.channels import BUILTIN_CHANNELS

        @dataclass
        class MockCfg2(ChannelConfig):
            pass

        BUILTIN_CHANNELS["mock_cfg2"] = MockConfigChannel

        mgr = ChannelManager(processor=_echo_processor, workers_per_channel=1)
        await mgr.start()
        try:
            ch_id = await mgr.add_channel("mock_cfg2", MockCfg2(channel_id="stable-id-123"))
            assert ch_id == "stable-id-123"
            assert mgr.get_channel("stable-id-123") is not None
        finally:
            await mgr.stop()
            BUILTIN_CHANNELS.pop("mock_cfg2", None)

    @pytest.mark.asyncio
    async def test_explicit_tenant_id_kwarg_overrides_config(self) -> None:
        """tenant_id kwarg to add_channel should override config.tenant_id."""
        from octop_gateway.channels import BUILTIN_CHANNELS

        @dataclass
        class MockCfg3(ChannelConfig):
            pass

        BUILTIN_CHANNELS["mock_cfg3"] = MockConfigChannel

        mgr = ChannelManager(processor=_echo_processor, workers_per_channel=1)
        await mgr.start()
        try:
            ch_id = await mgr.add_channel(
                "mock_cfg3",
                MockCfg3(tenant_id="from-config"),
                tenant_id="from-kwarg",
            )
            channel = mgr.get_channel(ch_id)
            assert channel is not None
            assert channel.tenant_id == "from-kwarg"
        finally:
            await mgr.stop()
            BUILTIN_CHANNELS.pop("mock_cfg3", None)


# ---------------------------------------------------------------------------
# Dict-config construction + probe credential validation
# ---------------------------------------------------------------------------


@dataclass
class _ProbeCfg(ChannelConfig):
    app_id: str = ""
    secret: str = ""


_ProbeCfg.field_aliases = {"client_secret": "secret"}
_ProbeCfg.required_credentials = ("app_id", "secret")


class _ProbeChannel(BaseChannel):
    """Mock channel with a typed config param to exercise dict→from_dict build."""

    channel_type = "probe_mock"

    def __init__(
        self,
        processor: MessageProcessor,
        config: _ProbeCfg | None = None,
        *,
        channel_id: str | None = None,
        tenant_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(processor, channel_id=channel_id, tenant_id=tenant_id)
        self.config = config
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def _send_text(self, subject: ChannelSubject, text: str) -> None:  # pragma: no cover
        pass

    async def _send_content(self, subject: ChannelSubject, parts: Any) -> None:  # pragma: no cover
        pass

    async def _send_media(self, subject: ChannelSubject, media: Any) -> None:  # pragma: no cover
        pass

    def parse_inbound(self, raw_payload: Any) -> InboundMessage:
        return InboundMessage(
            channel_id=self.channel_id,
            channel_type=self.channel_type,
            content=[TextContent(text=str(raw_payload))],
            channel_subject=ChannelSubject(subject_id="u1"),
        )


class TestDictConfigAndProbe:
    @pytest.mark.asyncio
    async def test_add_channel_builds_config_from_dict_with_alias(self) -> None:
        from octop_gateway.channels import BUILTIN_CHANNELS

        BUILTIN_CHANNELS["probe_mock"] = _ProbeChannel
        mgr = ChannelManager(processor=_echo_processor, workers_per_channel=1)
        await mgr.start()
        try:
            ch_id = await mgr.add_channel(
                "probe_mock",
                {"app_id": "  a  ", "client_secret": "sec"},
            )
            channel = mgr.get_channel(ch_id)
            assert isinstance(channel, _ProbeChannel)
            assert channel.config.app_id == "a"  # stripped
            assert channel.config.secret == "sec"  # alias mapped
        finally:
            await mgr.stop()
            BUILTIN_CHANNELS.pop("probe_mock", None)

    @pytest.mark.asyncio
    async def test_probe_channel_ok_starts_and_stops(self) -> None:
        from octop_gateway.channels import BUILTIN_CHANNELS

        BUILTIN_CHANNELS["probe_mock"] = _ProbeChannel
        mgr = ChannelManager(processor=_echo_processor, workers_per_channel=1)
        await mgr.start()
        try:
            await mgr.probe_channel("probe_mock", {"app_id": "a", "secret": "s"})
            assert mgr.get_channel("__probe__") is None  # not registered
        finally:
            await mgr.stop()
            BUILTIN_CHANNELS.pop("probe_mock", None)

    @pytest.mark.asyncio
    async def test_probe_channel_missing_credentials_raises(self) -> None:
        from octop_gateway.channel import ChannelCredentialsError
        from octop_gateway.channels import BUILTIN_CHANNELS

        BUILTIN_CHANNELS["probe_mock"] = _ProbeChannel
        mgr = ChannelManager(processor=_echo_processor, workers_per_channel=1)
        await mgr.start()
        try:
            with pytest.raises(ChannelCredentialsError) as exc:
                await mgr.probe_channel("probe_mock", {"app_id": "a"})
            assert exc.value.missing == ["secret"]
        finally:
            await mgr.stop()
            BUILTIN_CHANNELS.pop("probe_mock", None)

    @pytest.mark.asyncio
    async def test_add_channel_missing_credentials_raises(self) -> None:
        from octop_gateway.channel import ChannelCredentialsError
        from octop_gateway.channels import BUILTIN_CHANNELS

        BUILTIN_CHANNELS["probe_mock"] = _ProbeChannel
        mgr = ChannelManager(processor=_echo_processor, workers_per_channel=1)
        await mgr.start()
        try:
            with pytest.raises(ChannelCredentialsError) as exc:
                await mgr.add_channel("probe_mock", {"app_id": "a"})
            assert exc.value.missing == ["secret"]
        finally:
            await mgr.stop()
            BUILTIN_CHANNELS.pop("probe_mock", None)
