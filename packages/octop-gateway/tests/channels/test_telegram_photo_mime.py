"""Telegram SDK photos must retain an image MIME through download and storage."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram import Message

from octop_gateway.channels.telegram.channel import TelegramChannel, TelegramConfig
from octop_gateway.models import MessageEvent


@pytest.mark.parametrize(
    "data,expected_mime,extension",
    [
        (b"\xff\xd8\xff" + bytes(32), "image/jpeg", ".jpg"),
        (b"\x89PNG\r\n\x1a\n" + bytes(32), "image/png", ".png"),
        (b"GIF89a" + bytes(32), "image/gif", ".gif"),
        (b"GIF87a" + bytes(32), "image/gif", ".gif"),
        (b"RIFF" + bytes(4) + b"WEBP" + bytes(32), "image/webp", ".webp"),
    ],
)
@pytest.mark.parametrize("existing_mime", [None, "application/octet-stream", "image/jpeg"])
async def test_sdk_photo_mime_survives_persistence(data, expected_mime, extension, existing_mime):
    async def processor(message):
        yield MessageEvent.completed()

    channel = TelegramChannel(processor, config=TelegramConfig(bot_token="dummy"))
    message = Message.de_json(
        {
            "message_id": 1,
            "date": 0,
            "chat": {"id": 42, "type": "private"},
            "from": {"id": 7, "first_name": "Test", "is_bot": False},
            "photo": [{"file_id": "test", "file_unique_id": "test", "width": 1, "height": 1}],
        },
        None,
    )
    native = await channel._extract_message(message)
    assert native["media"][0]["mime_type"] == "image/jpeg"
    photo = native["content"][0]
    assert photo.mime_type is None
    photo.mime_type = existing_mime
    remote = SimpleNamespace(file_size=len(data), download_as_bytearray=AsyncMock(return_value=data))
    channel._app = SimpleNamespace(bot=SimpleNamespace(get_file=AsyncMock(return_value=remote)))
    channel._media_backend = SimpleNamespace(save=AsyncMock())
    await channel._persist_media_part(photo, 0, 123)
    assert photo.mime_type == expected_mime
    assert photo.local_path.endswith(extension)
    assert await channel.fetch_remote_media(photo.url) == (data, expected_mime)


@pytest.mark.parametrize(
    "data,mime", [(b"%PDF-1.7", "application/pdf"), (b"RIFF1234WAVE", "audio/wav"), (b"", "application/octet-stream")]
)
async def test_download_preserves_non_image_mime(data, mime):
    async def processor(message):
        yield MessageEvent.completed()

    channel = TelegramChannel(processor, config=TelegramConfig(bot_token="dummy"))
    channel._files["ref"] = ("file", mime)
    remote = SimpleNamespace(file_size=len(data), download_as_bytearray=AsyncMock(return_value=data))
    channel._app = SimpleNamespace(bot=SimpleNamespace(get_file=AsyncMock(return_value=remote)))
    assert await channel.fetch_remote_media(f"telegram-file://{channel.channel_id}/ref") == (data, mime)
