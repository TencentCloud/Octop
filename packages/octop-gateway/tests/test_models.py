"""Tests for octop_gateway.models."""

from __future__ import annotations

import time

from octop_gateway.models import (
    AudioContent,
    ChannelSubject,
    ContentType,
    FileContent,
    ImageContent,
    InboundMessage,
    MessageEvent,
    MessageEventType,
    TextContent,
    VideoContent,
)


class TestContentTypes:
    """Test content type models."""

    def test_text_content(self) -> None:
        tc = TextContent(text="hello")
        assert tc.type == ContentType.TEXT
        assert tc.text == "hello"

    def test_image_content(self) -> None:
        img = ImageContent(url="https://example.com/img.png", alt_text="cat")
        assert img.type == ContentType.IMAGE
        assert img.url == "https://example.com/img.png"
        assert img.alt_text == "cat"
        assert img.width is None

    def test_video_content(self) -> None:
        vid = VideoContent(url="https://example.com/vid.mp4", duration=5000)
        assert vid.type == ContentType.VIDEO
        assert vid.duration == 5000

    def test_audio_content(self) -> None:
        aud = AudioContent(url="https://example.com/audio.mp3", duration=3000)
        assert aud.type == ContentType.AUDIO
        assert aud.duration == 3000

    def test_file_content(self) -> None:
        fc = FileContent(url="https://example.com/doc.pdf", filename="doc.pdf", size=1024)
        assert fc.type == ContentType.FILE
        assert fc.filename == "doc.pdf"
        assert fc.size == 1024


class TestInboundMessage:
    """Test InboundMessage model."""

    def test_basic_creation(self) -> None:
        msg = InboundMessage(
            channel_id="test",
            content=[TextContent(text="hello world")],
            channel_subject=ChannelSubject(subject_id="user1"),
        )
        assert msg.channel_id == "test"
        assert msg.channel_subject is not None
        assert msg.channel_subject.subject_id == "user1"
        assert msg.text == "hello world"
        assert not msg.has_media

    def test_text_property_concatenates(self) -> None:
        msg = InboundMessage(
            channel_id="test",
            content=[
                TextContent(text="line 1"),
                TextContent(text="line 2"),
            ],
            channel_subject=ChannelSubject(subject_id="user1"),
        )
        assert msg.text == "line 1\nline 2"

    def test_has_media_with_image(self) -> None:
        msg = InboundMessage(
            channel_id="test",
            content=[
                TextContent(text="check this"),
                ImageContent(url="https://example.com/img.png"),
            ],
            channel_subject=ChannelSubject(subject_id="user1"),
        )
        assert msg.has_media

    def test_timestamp_default(self) -> None:
        before = time.time()
        msg = InboundMessage(
            channel_id="test",
            content=[TextContent(text="hi")],
            channel_subject=ChannelSubject(subject_id="user1"),
        )
        after = time.time()
        assert before <= msg.timestamp <= after


class TestMessageEvent:
    """Test MessageEvent model."""

    def test_text_factory(self) -> None:
        evt = MessageEvent.text("hello")
        assert evt.type == MessageEventType.MESSAGE
        assert len(evt.content) == 1
        assert isinstance(evt.content[0], TextContent)
        assert evt.content[0].text == "hello"

    def test_typing_factory(self) -> None:
        evt = MessageEvent.typing()
        assert evt.type == MessageEventType.TYPING
        assert evt.content == []

    def test_completed_factory(self) -> None:
        evt = MessageEvent.completed()
        assert evt.type == MessageEventType.COMPLETED

    def test_error_factory(self) -> None:
        evt = MessageEvent.error_event("something broke")
        assert evt.type == MessageEventType.ERROR
        assert evt.error == "something broke"


class TestLocalPath:
    """Test local_path field on media content types (MediaBackend keys)."""

    def test_image_default_none(self) -> None:
        img = ImageContent(url="https://example.com/img.png")
        assert img.local_path is None

    def test_image_set(self) -> None:
        img = ImageContent(url="https://example.com/img.png", local_path="images/abc.png")
        assert img.local_path == "images/abc.png"

    def test_image_url_optional(self) -> None:
        """A part can carry only local_path (no remote URL)."""
        img = ImageContent(local_path="images/abc.png")
        assert img.url == ""
        assert img.local_path == "images/abc.png"

    def test_file_set(self) -> None:
        fc = FileContent(filename="doc.pdf", local_path="files/doc.pdf")
        assert fc.local_path == "files/doc.pdf"
