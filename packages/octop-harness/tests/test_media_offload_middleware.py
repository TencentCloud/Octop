"""Tests for ``MediaOffloadMiddleware``."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from octop_harness.backends.workspace import BackendWorkspace
from octop_harness.middleware.media_offload import (
    MediaOffloadMiddleware,
    _ext_for_mime,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fs_backend(tmp_path: Path) -> Any:
    """Filesystem backend; workspace-relative paths map to host files under *tmp_path*."""
    from deepagents.backends import FilesystemBackend

    return FilesystemBackend(root_dir=str(tmp_path), virtual_mode=False)


@pytest.fixture
def workspace(fs_backend: Any, tmp_path: Path) -> BackendWorkspace:
    return BackendWorkspace(fs_backend, tmp_path)


def _offload_dir(tmp_path: Path) -> str:
    return str(tmp_path / ".media-cache")


def _state(messages: list[Any]) -> dict[str, Any]:
    return {"messages": messages}


def _b64(raw: bytes) -> str:
    return base64.standard_b64encode(raw).decode("ascii")


def _png(min_bytes: int = 8 * 1024) -> bytes:
    """A bytes blob of at least ``min_bytes`` so it crosses the offload threshold."""
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * max(0, min_bytes - 8)


def _image_block(raw: bytes, mime: str = "image/png") -> dict[str, Any]:
    return {"type": "image", "base64": _b64(raw), "mime_type": mime}


# ---------------------------------------------------------------------------
# First-pass behavior: tag in place, leave bytes inline
# ---------------------------------------------------------------------------


class TestFirstPass:
    def test_first_round_keeps_bytes_inline(self, workspace: BackendWorkspace, tmp_path: Path) -> None:
        """The first time a block is seen the model MUST still get the bytes,
        otherwise the agent never gets to analyze the image."""
        raw = _png(8 * 1024)
        mw = MediaOffloadMiddleware(workspace=workspace, min_bytes=4096)
        msg = HumanMessage(content=[_image_block(raw)])
        update = mw.before_model(_state([msg]), runtime=None)
        assert update is not None
        block = update["messages"][0].content[0]
        # Same base64 still here for the model.
        assert block["base64"] == _b64(raw)
        # But now stamped with the offload markers.
        sha = hashlib.sha256(raw).hexdigest()
        assert block["_offload_sha"] == sha
        assert block["_offload_path"] == f"{_offload_dir(tmp_path)}/{sha}.png"
        assert block["_offload_size"] == len(raw)
        assert block["_offload_mime"] == "image/png"

    def test_first_round_writes_real_bytes_to_backend(self, workspace: BackendWorkspace, tmp_path: Path) -> None:
        raw = _png(8 * 1024)
        mw = MediaOffloadMiddleware(workspace=workspace, min_bytes=4096)
        msg = HumanMessage(content=[_image_block(raw)])
        mw.before_model(_state([msg]), runtime=None)

        sha = hashlib.sha256(raw).hexdigest()
        # FilesystemBackend(virtual_mode=True) maps "/.media-cache/<sha>.png"
        # to "<tmp>/.media-cache/<sha>.png" on disk.
        ondisk = tmp_path / ".media-cache" / f"{sha}.png"
        assert ondisk.is_file()
        assert ondisk.read_bytes() == raw

    def test_first_round_audio_also_offloaded(self, workspace: BackendWorkspace, tmp_path: Path) -> None:
        raw = b"ID3" + b"\x00" * 8192
        mw = MediaOffloadMiddleware(workspace=workspace, min_bytes=4096)
        msg = HumanMessage(
            content=[{"type": "audio", "base64": _b64(raw), "mime_type": "audio/mpeg"}],
        )
        update = mw.before_model(_state([msg]), runtime=None)
        assert update is not None
        block = update["messages"][0].content[0]
        sha = hashlib.sha256(raw).hexdigest()
        assert block["_offload_path"] == f"{_offload_dir(tmp_path)}/{sha}.mp3"
        ondisk = tmp_path / ".media-cache" / f"{sha}.mp3"
        assert ondisk.read_bytes() == raw


# ---------------------------------------------------------------------------
# Second-pass behavior: tagged → placeholder
# ---------------------------------------------------------------------------


class TestSecondPass:
    def test_already_tagged_block_replaced_with_placeholder(self, workspace: BackendWorkspace, tmp_path: Path) -> None:
        """The agent re-enters before_model with a state containing a
        block that *already* carries offload markers (because we tagged
        it last turn). The model on this turn should get a text
        placeholder, not the base64."""
        raw = _png(8 * 1024)
        sha = hashlib.sha256(raw).hexdigest()
        path = f"{_offload_dir(tmp_path)}/{sha}.png"
        tagged = {
            "type": "image",
            "base64": _b64(raw),
            "mime_type": "image/png",
            "_offload_sha": sha,
            "_offload_path": path,
            "_offload_size": len(raw),
            "_offload_mime": "image/png",
        }
        mw = MediaOffloadMiddleware(workspace=workspace, min_bytes=4096)
        msg = HumanMessage(content=[tagged])
        update = mw.before_model(_state([msg]), runtime=None)
        assert update is not None
        block = update["messages"][0].content[0]
        assert block["type"] == "text"
        # Placeholder must mention how to retrieve, the SHA prefix, and the path.
        text = block["text"]
        assert "read_file" in text
        assert sha[:12] in text
        assert path in text

    def test_two_round_simulation_writes_once(self, workspace: BackendWorkspace, fs_backend: Any) -> None:
        """End-to-end: round 1 inline+tagged, round 2 placeholder.
        backend.upload_files should be invoked exactly once."""
        raw = _png(8 * 1024)
        mw = MediaOffloadMiddleware(workspace=workspace, min_bytes=4096)

        with patch.object(fs_backend, "upload_files", wraps=fs_backend.upload_files) as spy:
            msg1 = HumanMessage(content=[_image_block(raw)])
            r1 = mw.before_model(_state([msg1]), runtime=None)
            assert r1 is not None
            tagged_msg = r1["messages"][0]

            # Round 2: the tagged message is what's now in state.
            r2 = mw.before_model(_state([tagged_msg]), runtime=None)
            assert r2 is not None
            assert r2["messages"][0].content[0]["type"] == "text"

        # Wrote bytes only on round 1.
        assert spy.call_count == 1


# ---------------------------------------------------------------------------
# Skipped cases
# ---------------------------------------------------------------------------


class TestSkipped:
    def test_under_min_bytes_left_inline(self, workspace: BackendWorkspace) -> None:
        # Decoded payload is 12 bytes, far below 4 KiB threshold.
        raw = b"\x89PNG\r\n\x1a\n\x00\x00\x00\x00"
        mw = MediaOffloadMiddleware(workspace=workspace, min_bytes=4096)
        msg = HumanMessage(content=[_image_block(raw)])
        update = mw.before_model(_state([msg]), runtime=None)
        assert update is None  # nothing changed

    def test_text_block_passthrough(self, workspace: BackendWorkspace) -> None:
        mw = MediaOffloadMiddleware(workspace=workspace, min_bytes=4096)
        msg = HumanMessage(content=[{"type": "text", "text": "hi there"}])
        update = mw.before_model(_state([msg]), runtime=None)
        assert update is None

    def test_string_content_passthrough(self, workspace: BackendWorkspace) -> None:
        mw = MediaOffloadMiddleware(workspace=workspace, min_bytes=4096)
        msg = HumanMessage(content="just a string")
        update = mw.before_model(_state([msg]), runtime=None)
        assert update is None

    def test_image_url_below_min_bytes_left_alone(self, workspace: BackendWorkspace) -> None:
        """``image_url`` blocks are now offloadable in principle, but a 3-byte
        payload still falls under ``min_bytes`` and stays inline."""
        mw = MediaOffloadMiddleware(workspace=workspace, min_bytes=4096)
        block = {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,AAAA"},
        }
        msg = HumanMessage(content=[block])
        update = mw.before_model(_state([msg]), runtime=None)
        assert update is None

    def test_anthropic_source_block_left_alone(self, workspace: BackendWorkspace) -> None:
        """Anthropic-native ``source: {type: base64, ...}`` blocks belong to
        the provider transport layer; not our concern."""
        mw = MediaOffloadMiddleware(workspace=workspace, min_bytes=4096)
        block = {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"},
        }
        msg = HumanMessage(content=[block])
        update = mw.before_model(_state([msg]), runtime=None)
        assert update is None

    def test_video_left_alone(self, workspace: BackendWorkspace) -> None:
        """Video offload is intentionally unsupported — even via
        read_file the bytes still pass through prompts. Push video
        handling to a provider files API later."""
        mw = MediaOffloadMiddleware(workspace=workspace, min_bytes=4096)
        raw = b"\x00" * 8192
        block = {"type": "video", "base64": _b64(raw), "mime_type": "video/mp4"}
        msg = HumanMessage(content=[block])
        update = mw.before_model(_state([msg]), runtime=None)
        assert update is None

    def test_file_block_left_alone(self, workspace: BackendWorkspace) -> None:
        # PDF and other generic files are routed via deepagents read_file
        # already; we only care about image / audio in messages.
        mw = MediaOffloadMiddleware(workspace=workspace, min_bytes=4096)
        raw = b"%PDF-1.4" + b"\x00" * 8192
        block = {"type": "file", "base64": _b64(raw), "mime_type": "application/pdf"}
        msg = HumanMessage(content=[block])
        update = mw.before_model(_state([msg]), runtime=None)
        assert update is None

    def test_invalid_base64_left_alone(self, workspace: BackendWorkspace) -> None:
        mw = MediaOffloadMiddleware(workspace=workspace, min_bytes=4096)
        # base64.b64decode is permissive, but our validate=False call still
        # tolerates this; the size check then trips because bytes are tiny.
        # We use an obviously-wrong type to ensure the early "not isinstance str"
        # branch fires.
        msg = HumanMessage(
            content=[{"type": "image", "base64": None, "mime_type": "image/png"}],  # type: ignore[dict-item]
        )
        update = mw.before_model(_state([msg]), runtime=None)
        assert update is None


# ---------------------------------------------------------------------------
# OpenAI image_url compatibility (legacy / bridge-emitted blocks)
# ---------------------------------------------------------------------------


class TestImageUrlCompat:
    """Bridges and hand-crafted OpenAI requests sometimes emit
    ``{type: image_url, image_url: {url: data:...}}`` blocks instead of
    the v1 standard. Middleware should offload those too so a single
    long thread can be cleaned up regardless of who built the message.
    """

    def _data_uri_block(self, raw: bytes, mime: str = "image/png") -> dict[str, Any]:
        b64 = _b64(raw)
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        }

    def test_first_round_keeps_url_inline_and_tags(self, workspace: BackendWorkspace, tmp_path: Path) -> None:
        raw = _png(8 * 1024)
        mw = MediaOffloadMiddleware(workspace=workspace, min_bytes=4096)
        msg = HumanMessage(content=[self._data_uri_block(raw)])
        update = mw.before_model(_state([msg]), runtime=None)
        assert update is not None

        block = update["messages"][0].content[0]
        # The original transport shape is preserved this turn so the
        # provider conversion layer still sees something it understands.
        assert block["type"] == "image_url"
        assert block["image_url"]["url"].startswith("data:image/png;base64,")
        # And the offload markers are stamped on for next round.
        sha = hashlib.sha256(raw).hexdigest()
        assert block["_offload_sha"] == sha
        assert block["_offload_path"] == f"{_offload_dir(tmp_path)}/{sha}.png"
        assert block["_offload_btype"] == "image"
        # Bytes really hit disk.
        assert (tmp_path / ".media-cache" / f"{sha}.png").read_bytes() == raw

    def test_second_round_replaced_with_placeholder(self, workspace: BackendWorkspace, tmp_path: Path) -> None:
        raw = _png(8 * 1024)
        sha = hashlib.sha256(raw).hexdigest()
        path = f"{_offload_dir(tmp_path)}/{sha}.png"
        # Simulate state after a prior round.
        tagged = {
            **self._data_uri_block(raw),
            "_offload_sha": sha,
            "_offload_path": path,
            "_offload_size": len(raw),
            "_offload_mime": "image/png",
            "_offload_btype": "image",
        }
        mw = MediaOffloadMiddleware(workspace=workspace, min_bytes=4096)
        msg = HumanMessage(content=[tagged])
        update = mw.before_model(_state([msg]), runtime=None)
        assert update is not None
        block = update["messages"][0].content[0]
        assert block["type"] == "text"
        # Placeholder labels itself as "image" (not "image_url"), since the
        # transport shape is irrelevant to operators reading the transcript.
        assert "image offloaded" in block["text"]
        assert sha[:12] in block["text"]
        assert path in block["text"]

    def test_https_url_left_inline(self, workspace: BackendWorkspace) -> None:
        """Remote URLs don't bloat the prompt by themselves; nothing to do."""
        mw = MediaOffloadMiddleware(workspace=workspace, min_bytes=4096)
        block = {
            "type": "image_url",
            "image_url": {"url": "https://example.com/cat.png"},
        }
        msg = HumanMessage(content=[block])
        update = mw.before_model(_state([msg]), runtime=None)
        assert update is None

    def test_data_uri_without_base64_param_left_inline(self, workspace: BackendWorkspace) -> None:
        """Plain ``data:`` URIs (no ``;base64,``) are exotic enough that
        we'd rather skip than guess at the encoding."""
        mw = MediaOffloadMiddleware(workspace=workspace, min_bytes=4096)
        block = {
            "type": "image_url",
            "image_url": {"url": "data:text/plain,hello"},
        }
        msg = HumanMessage(content=[block])
        update = mw.before_model(_state([msg]), runtime=None)
        assert update is None

    def test_image_url_string_payload_supported(self, workspace: BackendWorkspace) -> None:
        """Some legacy code paths set ``image_url`` to a bare string."""
        raw = _png(8 * 1024)
        b64 = _b64(raw)
        block = {
            "type": "image_url",
            "image_url": f"data:image/png;base64,{b64}",
        }
        mw = MediaOffloadMiddleware(workspace=workspace, min_bytes=4096)
        msg = HumanMessage(content=[block])
        update = mw.before_model(_state([msg]), runtime=None)
        assert update is not None
        assert update["messages"][0].content[0]["_offload_sha"]

    def test_data_uri_with_charset_param(self, workspace: BackendWorkspace) -> None:
        """``data:image/png;charset=binary;base64,...`` should still parse."""
        raw = _png(8 * 1024)
        b64 = _b64(raw)
        block = {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;charset=binary;base64,{b64}"},
        }
        mw = MediaOffloadMiddleware(workspace=workspace, min_bytes=4096)
        msg = HumanMessage(content=[block])
        update = mw.before_model(_state([msg]), runtime=None)
        assert update is not None
        assert update["messages"][0].content[0]["_offload_mime"] == "image/png"


# ---------------------------------------------------------------------------
# Cross-message / multi-role behavior
# ---------------------------------------------------------------------------


class TestMultiMessage:
    def test_handles_tool_message_blocks(self, workspace: BackendWorkspace) -> None:
        """``read_file`` produces a ToolMessage with image content_blocks.
        That should also be offloaded."""
        raw = _png(8 * 1024)
        mw = MediaOffloadMiddleware(workspace=workspace, min_bytes=4096)
        tool_msg = ToolMessage(
            content=[_image_block(raw)],
            tool_call_id="abc",
            name="read_file",
        )
        update = mw.before_model(_state([tool_msg]), runtime=None)
        assert update is not None
        assert update["messages"][0].content[0]["_offload_sha"]

    def test_handles_ai_message_blocks(self, workspace: BackendWorkspace) -> None:
        # AIMessage rarely carries inline media but it's a valid shape.
        raw = _png(8 * 1024)
        mw = MediaOffloadMiddleware(workspace=workspace, min_bytes=4096)
        ai = AIMessage(content=[_image_block(raw)])
        update = mw.before_model(_state([ai]), runtime=None)
        assert update is not None

    def test_dedupe_same_image_in_two_messages(self, workspace: BackendWorkspace, tmp_path: Path) -> None:
        """Two messages, same image bytes — same SHA, same path. Backend
        still gets a write per message in this naive impl, but both
        messages tag to the same path so a future read is consistent."""
        raw = _png(8 * 1024)
        mw = MediaOffloadMiddleware(workspace=workspace, min_bytes=4096)
        m1 = HumanMessage(content=[_image_block(raw)])
        m2 = HumanMessage(content=[_image_block(raw)])
        update = mw.before_model(_state([m1, m2]), runtime=None)
        assert update is not None
        sha = hashlib.sha256(raw).hexdigest()
        path = f"{_offload_dir(tmp_path)}/{sha}.png"
        assert update["messages"][0].content[0]["_offload_path"] == path
        assert update["messages"][1].content[0]["_offload_path"] == path
        # File on disk has the right bytes regardless of how many writes happened.
        assert (tmp_path / ".media-cache" / f"{sha}.png").read_bytes() == raw

    def test_backend_error_keeps_block_inline(self, workspace: BackendWorkspace, fs_backend: Any) -> None:
        """If the backend write returns an error response, we leave the
        block untouched rather than break the turn."""
        raw = _png(8 * 1024)
        mw = MediaOffloadMiddleware(workspace=workspace, min_bytes=4096)

        # Make upload_files report a per-file error.
        from deepagents.backends.protocol import FileUploadResponse

        def fake_upload(files: list[tuple[str, bytes]]) -> list[Any]:
            return [FileUploadResponse(path=p, error="permission_denied") for p, _ in files]

        with patch.object(fs_backend, "upload_files", side_effect=fake_upload):
            msg = HumanMessage(content=[_image_block(raw)])
            update = mw.before_model(_state([msg]), runtime=None)
        # No tagging happened → no state update emitted.
        assert update is None

    def test_backend_exception_keeps_block_inline(self, workspace: BackendWorkspace, fs_backend: Any) -> None:
        raw = _png(8 * 1024)
        mw = MediaOffloadMiddleware(workspace=workspace, min_bytes=4096)
        with patch.object(fs_backend, "upload_files", side_effect=OSError("disk full")):
            msg = HumanMessage(content=[_image_block(raw)])
            update = mw.before_model(_state([msg]), runtime=None)
        assert update is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestExtForMime:
    def test_known_overrides(self) -> None:
        assert _ext_for_mime("image/png", default=".bin") == ".png"
        assert _ext_for_mime("image/jpeg", default=".bin") == ".jpg"
        assert _ext_for_mime("audio/mpeg", default=".bin") == ".mp3"
        assert _ext_for_mime("audio/wav", default=".bin") == ".wav"

    def test_falls_back_to_default(self) -> None:
        assert _ext_for_mime("application/x-weird", default=".bin") == ".bin"

    def test_strips_parameters(self) -> None:
        assert _ext_for_mime("image/png; charset=binary", default=".bin") == ".png"


# ---------------------------------------------------------------------------
# Construction errors
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_invalid_min_bytes(self, workspace: BackendWorkspace) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            MediaOffloadMiddleware(workspace=workspace, min_bytes=0)


# ---------------------------------------------------------------------------
# Integration with HarnessAgent
# ---------------------------------------------------------------------------


class TestAgentIntegration:
    def test_installed_by_default(self, tmp_path: Path) -> None:
        from octop_harness.agent import HarnessAgent
        from octop_harness.config import (
            HarnessAgentConfig,
            ModelConfig,
            ProviderConfig,
        )

        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": True},
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="https://x",
                    api_key="k",
                    models=[ModelConfig(id="text")],
                ),
            ],
            default_model="p/text",
        )
        captured: dict[str, Any] = {}

        def fake_create(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return MagicMock(name="fake-graph")

        with (
            patch("langchain_openai.ChatOpenAI", return_value=MagicMock()),
            patch("deepagents.create_deep_agent", side_effect=fake_create),
        ):
            HarnessAgent(cfg)

        mw_classes = [type(m).__name__ for m in captured["middleware"]]
        assert "MediaOffloadMiddleware" in mw_classes

    def test_can_be_disabled(self, tmp_path: Path) -> None:
        from octop_harness.agent import HarnessAgent
        from octop_harness.config import (
            HarnessAgentConfig,
            ModelConfig,
            ProviderConfig,
        )

        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": True},
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="https://x",
                    api_key="k",
                    models=[ModelConfig(id="text")],
                ),
            ],
            default_model="p/text",
            media_offload_enabled=False,
        )
        captured: dict[str, Any] = {}

        def fake_create(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return MagicMock(name="fake-graph")

        with (
            patch("langchain_openai.ChatOpenAI", return_value=MagicMock()),
            patch("deepagents.create_deep_agent", side_effect=fake_create),
        ):
            HarnessAgent(cfg)

        mw_classes = [type(m).__name__ for m in captured["middleware"]]
        assert "MediaOffloadMiddleware" not in mw_classes
