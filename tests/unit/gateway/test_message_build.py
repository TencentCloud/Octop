"""tests/unit/test_message_build.py"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from octop_gateway.models import ImageContent, TextContent

from octop.infra.gateway.media.tool_media import iter_media_blocks
from octop.infra.gateway.process import (
    build_content,
    build_harness_request,
    content_from_parts,
)


def test_build_content_text_only():
    assert build_content(text="hello") == "hello"


def test_build_content_with_image_url():
    blocks = build_content(text="see", images=[{"type": "image", "url": "http://x"}])
    assert isinstance(blocks, list)
    assert blocks[0]["type"] == "text"
    assert blocks[1]["url"] == "http://x"


def test_build_content_with_image_data():
    payload = base64.b64encode(b"png-bytes").decode()
    blocks = build_content(
        text="see",
        images=[ImageContent(data=payload, mime_type="image/png")],
    )
    assert isinstance(blocks, list)
    img_block = blocks[1]
    assert img_block["type"] == "image_url"
    assert img_block["image_url"]["url"] == f"data:image/png;base64,{payload}"


def test_build_content_reads_media_backend_key(tmp_path: Path) -> None:
    from octop_gateway.media import FileSystemMediaBackend

    media_root = tmp_path / "media"
    media_root.mkdir()
    key = "inbound/photo.png"
    (media_root / "inbound").mkdir()
    (media_root / key).write_bytes(b"img")
    backend = FileSystemMediaBackend(str(media_root))

    blocks = build_content(
        text="see",
        images=[ImageContent(local_path=key, mime_type="image/png")],
        media_backend=backend,
    )
    assert isinstance(blocks, list)
    expected_b64 = base64.b64encode(b"img").decode()
    assert blocks[1]["type"] == "image_url"
    assert blocks[1]["image_url"]["url"] == f"data:image/png;base64,{expected_b64}"


def test_iter_media_blocks_from_json_string():
    blocks = iter_media_blocks(
        '{"type": "image", "source": {"type": "url", "url": "https://x/a.png"}}'
    )
    assert len(blocks) == 1
    assert blocks[0]["type"] == "image"


def test_content_from_parts_text_and_image():
    payload = content_from_parts(
        [TextContent(text="see"), ImageContent(url="http://x")],
    )
    assert isinstance(payload, list)
    assert payload[0]["text"] == "see"
    assert payload[1]["type"] == "image_url"
    assert payload[1]["image_url"]["url"] == "http://x"


def test_build_harness_request_with_messages_override():
    req = build_harness_request(
        thread_id="t1",
        user_id=1,
        source="cron",
        messages=[{"role": "user", "content": "ping"}],
    )
    assert req["messages"] == [{"role": "user", "content": "ping"}]
    assert req["thread_id"] == "t1"


@pytest.mark.asyncio
async def test_block_to_content_part_base64_image():
    from tests.support.fakes import FakeHarnessAgent

    from octop.infra.gateway.media.tool_media import block_to_content_part

    part = await block_to_content_part(
        {
            "type": "image",
            "source": {"type": "base64", "data": "aGVsbG8=", "media_type": "image/png"},
        },
        workspace=FakeHarnessAgent().workspace,
    )
    assert isinstance(part, ImageContent)
    assert part.data == "aGVsbG8="
    assert part.mime_type == "image/png"
