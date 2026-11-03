"""Tests for the standalone image-inspector tool plugin."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from langchain_core.tools import StructuredTool
from octop_harness.plugins import PluginRegistry, build_plugin_tools, load_plugin_dir
from PIL import Image

_PLUGIN_DIR = Path(__file__).resolve().parents[2] / "plugins" / "image-inspector"


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    PluginRegistry.reset()
    yield
    PluginRegistry.reset()


def test_plugin_loads_and_registers_inspect_image() -> None:
    loaded = load_plugin_dir(_PLUGIN_DIR, install_deps=False)

    assert loaded.manifest.id == "image-inspector"
    assert loaded.manifest.kind == "tool"
    assert [tool.name for tool in loaded.tools] == ["inspect_image"]

    tools = build_plugin_tools(global_plugins={"image-inspector": True})
    assert len(tools) == 1
    assert isinstance(tools[0], StructuredTool)
    assert "generate_image" in tools[0].description


class _FakeModelAccess:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[list[Any], dict[str, Any]]] = []

    async def ainvoke(self, messages: list[Any], **kwargs: Any) -> str:
        self.calls.append((messages, kwargs))
        return self.response


class _FakeModelFactory:
    def __init__(self, access: _FakeModelAccess) -> None:
        self.access = access
        self.specs: list[tuple[Any, dict[str, Any]]] = []

    def get_for(
        self,
        spec: Any,
        *,
        get_protocol: Any = None,
        **kwargs: Any,
    ) -> _FakeModelAccess:
        self.specs.append((spec, kwargs))
        return self.access


def _image_tool(
    response: str = "Visual review result",
) -> tuple[StructuredTool, _FakeModelAccess, _FakeModelFactory]:
    loaded = load_plugin_dir(_PLUGIN_DIR, install_deps=False)
    assert [tool.name for tool in loaded.tools] == ["inspect_image"]
    access = _FakeModelAccess(response)
    factory = _FakeModelFactory(access)
    assert loaded.context is not None
    loaded.context.bind_model_factory(factory)
    tools = build_plugin_tools(global_plugins={"image-inspector": True})
    assert len(tools) == 1
    return tools[0], access, factory


def _workspace_image(
    tmp_path: Path,
    *,
    fmt: str = "PNG",
    suffix: str = ".png",
) -> Path:
    path = tmp_path / "workspaces" / "main" / "generated" / f"image{suffix}"
    path.parent.mkdir(parents=True)
    Image.new("RGB", (2, 3), (255, 0, 0)).save(path, format=fmt)
    return path


async def test_inspect_image_calls_multimodal_model_and_returns_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    image_path = _workspace_image(tmp_path)
    tool, access, factory = _image_tool("Layout is clean; no clipping detected.")

    result = await tool.ainvoke({"path": str(image_path), "focus": "check clipping and alignment"})

    assert result == "Layout is clean; no clipping detected."
    assert factory.specs[0][0] == "auto"
    assert "messages" in factory.specs[0][1]
    assert len(access.calls) == 1
    messages = access.calls[0][0]
    human_content = messages[1].content
    assert isinstance(human_content, list)
    image_blocks = [block for block in human_content if block["type"] == "image_url"]
    assert len(image_blocks) == 1
    assert image_blocks[0]["image_url"]["url"].startswith("data:image/png;base64,")
    text_blocks = [block for block in human_content if block["type"] == "text"]
    assert "check clipping and alignment" in text_blocks[0]["text"]


@pytest.mark.parametrize(
    ("fmt", "suffix", "expected_media_type"),
    [
        ("JPEG", ".jpg", "image/jpeg"),
        ("WEBP", ".webp", "image/webp"),
    ],
)
async def test_inspect_image_supports_common_raster_formats(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fmt: str,
    suffix: str,
    expected_media_type: str,
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    image_path = _workspace_image(tmp_path, fmt=fmt, suffix=suffix)

    tool, access, _ = _image_tool()
    result = await tool.ainvoke({"path": str(image_path)})

    assert result == "Visual review result"
    human_content = access.calls[0][0][1].content
    image_block = next(block for block in human_content if block["type"] == "image_url")
    assert image_block["image_url"]["url"].startswith(f"data:{expected_media_type};base64,")


async def test_inspect_image_rejects_outside_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    outside = tmp_path / "outside.png"
    Image.new("RGB", (1, 1)).save(outside, format="PNG")

    tool, access, _ = _image_tool()
    result = await tool.ainvoke({"path": str(outside)})

    assert isinstance(result, str)
    assert result.startswith("Error: path is outside")
    assert access.calls == []


async def test_inspect_image_rejects_missing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    path = tmp_path / "workspaces" / "main" / "generated" / "missing.png"

    tool, access, _ = _image_tool()
    result = await tool.ainvoke({"path": str(path)})

    assert isinstance(result, str)
    assert "image file not found" in result
    assert access.calls == []


async def test_inspect_image_rejects_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    path = tmp_path / "workspaces" / "main" / "generated" / "folder.png"
    path.mkdir(parents=True)

    tool, access, _ = _image_tool()
    result = await tool.ainvoke({"path": str(path)})

    assert isinstance(result, str)
    assert "not a regular image file" in result
    assert access.calls == []


async def test_inspect_image_rejects_unsupported_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    path = tmp_path / "workspaces" / "main" / "generated" / "not-image.png"
    path.parent.mkdir(parents=True)
    path.write_text("plain text", encoding="utf-8")

    tool, access, _ = _image_tool()
    result = await tool.ainvoke({"path": str(path)})

    assert isinstance(result, str)
    assert "unsupported image format" in result
    assert access.calls == []


async def test_inspect_image_rejects_oversized_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    image_path = _workspace_image(tmp_path)
    tool, access, _ = _image_tool()
    module = sys.modules["harness_plugin_image_inspector"]
    monkeypatch.setattr(module, "_MAX_IMAGE_BYTES", 1)

    result = await tool.ainvoke({"path": str(image_path)})

    assert isinstance(result, str)
    assert "too large" in result
    assert access.calls == []
