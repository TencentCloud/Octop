"""Tests for ``send_file_to_user`` and ``desktop_screenshot``."""

from __future__ import annotations

import os
import platform
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from octop_harness.backends.workspace import BackendWorkspace
from octop_harness.builtin.tools.desktop_screenshot import (
    DEFAULT_SCREENSHOTS_DIR,
    build_desktop_screenshot_tool,
    desktop_screenshot,
)
from octop_harness.builtin.tools.send_file import send_file_to_user


class TestSendFileToUser:
    def test_image_block(self, tmp_path: Path) -> None:
        target = tmp_path / "shot.png"
        target.write_bytes(b"\x89PNG\r\n\x1a\n")  # PNG magic bytes
        block = send_file_to_user.invoke({"file_path": str(target)})
        assert block["type"] == "image"
        assert block["filename"] == "shot.png"
        assert block["source"]["type"] == "url"
        assert block["source"]["url"].startswith("file://")
        assert block["source"]["url"].endswith("shot.png")
        assert block["source"]["media_type"] == "image/png"

    def test_audio_block(self, tmp_path: Path) -> None:
        target = tmp_path / "voice.mp3"
        target.write_bytes(b"ID3\x04\x00")
        block = send_file_to_user.invoke({"file_path": str(target)})
        assert block["type"] == "audio"
        assert block["source"]["media_type"] == "audio/mpeg"

    def test_video_block(self, tmp_path: Path) -> None:
        target = tmp_path / "clip.mp4"
        target.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        block = send_file_to_user.invoke({"file_path": str(target)})
        assert block["type"] == "video"

    def test_unknown_extension_falls_back_to_file(self, tmp_path: Path) -> None:
        target = tmp_path / "data.bin"
        target.write_bytes(b"\x00")
        block = send_file_to_user.invoke({"file_path": str(target)})
        assert block["type"] == "file"
        assert block["source"]["media_type"] == "application/octet-stream"

    def test_missing_path_returns_recoverable_error(self, tmp_path: Path) -> None:
        content = send_file_to_user.invoke({"file_path": str(tmp_path / "nope.png")})
        assert isinstance(content, str)
        assert "no such file" in content
        assert "workspace-relative" in content

    def test_directory_returns_recoverable_error(self, tmp_path: Path) -> None:
        content = send_file_to_user.invoke({"file_path": str(tmp_path)})
        assert isinstance(content, str)
        assert "not a regular file" in content

    def test_bound_missing_path_does_not_crash_tool_node(self, tmp_path: Path) -> None:
        from deepagents.backends import FilesystemBackend
        from langchain_core.messages import ToolMessage
        from langgraph.prebuilt.tool_node import ToolCallRequest, ToolNode

        from octop_harness.builtin.tools.send_file import build_send_file_to_user_tool

        backend = FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)
        tool = build_send_file_to_user_tool(BackendWorkspace(backend, tmp_path))
        node = ToolNode([tool])
        call = {
            "name": "send_file_to_user",
            "args": {"file_path": ".octop/generated/missing.xlsx"},
            "id": "call_1",
            "type": "tool_call",
        }
        req = ToolCallRequest(tool_call=call, tool=tool, state={"messages": []}, runtime=None)
        msg = node._execute_tool_sync(req, "dict", {})
        assert isinstance(msg, ToolMessage)
        assert msg.status == "error"
        assert "no such file" in str(msg.content)

    def test_relative_path_resolves(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        target = tmp_path / "rel.png"
        target.write_bytes(b"\x89PNG\r\n\x1a\n")
        monkeypatch.chdir(tmp_path)
        block = send_file_to_user.invoke({"file_path": "rel.png"})
        assert block["path"] == "rel.png"
        assert block["source"]["url"].endswith("rel.png")
        assert os.path.isabs(block["source"]["url"].removeprefix("file://"))

    def test_workspace_relative_via_bound_tool(self, tmp_path: Path) -> None:
        from deepagents.backends import FilesystemBackend

        from octop_harness.builtin.tools.send_file import build_send_file_to_user_tool

        backend = FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)
        ws = BackendWorkspace(backend, tmp_path)
        (tmp_path / "generated").mkdir()
        target = tmp_path / "generated" / "shot.png"
        target.write_bytes(b"\x89PNG\r\n\x1a\n")
        tool = build_send_file_to_user_tool(ws)
        block = tool.invoke({"file_path": "generated/shot.png"})
        assert block["filename"] == "shot.png"
        assert block["path"] == "generated/shot.png"
        assert block["source"]["url"] == target.resolve().as_uri()

    def test_virtual_absolute_via_bound_tool_with_scoped_backend_mount(
        self,
        tmp_path: Path,
    ) -> None:
        from deepagents.backends import FilesystemBackend

        from octop_harness.builtin.tools.send_file import build_send_file_to_user_tool

        root = tmp_path / "root"
        workspace = tmp_path / "workspace"
        root.mkdir()
        workspace.mkdir()
        (root / "generated").mkdir()
        target = root / "generated" / "deck.pptx"
        target.write_bytes(b"pptx-bytes")
        backend = FilesystemBackend(root_dir=str(root), virtual_mode=True)
        ws = BackendWorkspace(backend, workspace)
        tool = build_send_file_to_user_tool(ws)
        block = tool.invoke({"file_path": "/generated/deck.pptx"})
        assert block["filename"] == "deck.pptx"
        assert block["path"] == "/generated/deck.pptx"
        assert block["source"]["url"] == target.resolve().as_uri()
        assert ws.materialize_local("/generated/deck.pptx") == target.resolve()

    def test_bound_tool_relative_prefers_backend_mount_over_process_cwd(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Relative paths must not resolve against the Octop process cwd."""
        from deepagents.backends import FilesystemBackend

        from octop_harness.builtin.tools.send_file import build_send_file_to_user_tool

        root = tmp_path / "root"
        workspace = tmp_path / "agent_ws"
        proc_cwd = tmp_path / "octop_repo"
        root.mkdir()
        workspace.mkdir()
        proc_cwd.mkdir()
        (proc_cwd / "workspace").mkdir()
        (proc_cwd / "workspace" / "Sapiens.pptx").write_bytes(b"decoy")
        (root / "workspace").mkdir()
        real = root / "workspace" / "Sapiens.pptx"
        real.write_bytes(b"pptx-bytes")
        monkeypatch.chdir(proc_cwd)

        backend = FilesystemBackend(root_dir=str(root), virtual_mode=True)
        tool = build_send_file_to_user_tool(BackendWorkspace(backend, workspace))
        block = tool.invoke({"file_path": "workspace/Sapiens.pptx"})
        assert block["path"] == "workspace/Sapiens.pptx"
        assert block["source"]["url"] == real.resolve().as_uri()
        from urllib.parse import urlparse

        parsed = urlparse(block["source"]["url"])
        assert parsed.scheme == "file"
        assert parsed.netloc in ("", "localhost")
        assert Path(parsed.path).resolve() == real.resolve()

    def test_bound_tool_missing_relative_skips_process_cwd(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from deepagents.backends import FilesystemBackend

        from octop_harness.builtin.tools.send_file import build_send_file_to_user_tool

        root = tmp_path / "root"
        workspace = tmp_path / "agent_ws"
        proc_cwd = tmp_path / "octop_repo"
        root.mkdir()
        workspace.mkdir()
        proc_cwd.mkdir()
        monkeypatch.chdir(proc_cwd)

        backend = FilesystemBackend(root_dir=str(root), virtual_mode=True)
        tool = build_send_file_to_user_tool(BackendWorkspace(backend, workspace))
        content = tool.invoke({"file_path": "workspace/missing.pptx"})
        assert isinstance(content, str)
        assert "no such file" in content
        assert str(proc_cwd) not in content

    def test_host_fallback_when_file_only_on_real_disk(self, tmp_path: Path) -> None:
        from deepagents.backends import FilesystemBackend

        from octop_harness.builtin.tools.send_file import build_send_file_to_user_tool

        root = tmp_path / "root"
        workspace = tmp_path / "workspace"
        root.mkdir()
        workspace.mkdir()
        only_host = workspace / "outbound.png"
        only_host.write_bytes(b"\x89PNG\r\n\x1a\n")
        backend = FilesystemBackend(root_dir=str(root), virtual_mode=True)
        ws = BackendWorkspace(backend, workspace)
        tool = build_send_file_to_user_tool(ws)
        emitted = str(only_host)
        block = tool.invoke({"file_path": emitted})
        assert block["path"] == emitted
        assert block["source"]["url"] == Path(emitted).as_uri()

    def test_bound_tool_does_not_rewrite_host_path_into_root(self, tmp_path: Path) -> None:
        """Emit caller's path even when bytes live under virtual nest."""
        from deepagents.backends import FilesystemBackend

        from octop_harness.builtin.tools.send_file import build_send_file_to_user_tool

        root = tmp_path / "root"
        workspace = tmp_path / "workspace"
        root.mkdir()
        workspace.mkdir()
        hostish = "/Users/demo/workspace/Sapiens.pptx"
        nest = root / "Users/demo/workspace/Sapiens.pptx"
        nest.parent.mkdir(parents=True)
        nest.write_bytes(b"pptx")
        backend = FilesystemBackend(root_dir=str(root), virtual_mode=True)
        tool = build_send_file_to_user_tool(BackendWorkspace(backend, workspace))
        block = tool.invoke({"file_path": hostish})
        assert block["path"] == hostish
        # ``path`` keeps the caller key; ``url`` is the materialized on-disk URI.
        assert block["source"]["url"] == nest.resolve().as_uri()
        assert Path(hostish).as_uri() != block["source"]["url"]


class TestDesktopScreenshot:
    """Capture is heavily mocked — no real screenshots in CI."""

    @staticmethod
    def _fake_mss_module(shot_fn: object | None = None) -> MagicMock:
        class _FakeMss:
            def __init__(self, *, backend: str = "default", display: str | None = None) -> None:
                self.backend = backend
                self.display = display

            def shot(self, *, mon: int, output: str) -> None:
                if shot_fn is not None:
                    shot_fn(mon=mon, output=output)  # type: ignore[operator]
                else:
                    Path(output).write_bytes(b"\x89PNG\r\n\x1a\n")

            def close(self) -> None:
                """No-op."""

        fake_module = MagicMock()
        fake_module.MSS = _FakeMss
        return fake_module

    @staticmethod
    def _workspace(tmp_path: Path) -> BackendWorkspace:
        from deepagents.backends import FilesystemBackend

        backend = FilesystemBackend(root_dir=str(tmp_path), virtual_mode=False)
        return BackendWorkspace(backend, tmp_path)

    def test_full_screen_via_mss(self, tmp_path: Path) -> None:
        target = tmp_path / "shot.png"
        with (
            patch.dict("sys.modules", {"mss": self._fake_mss_module()}),
            patch(
                "octop_harness.builtin.tools.desktop_screenshot.shutil.which",
                return_value=None,
            ),
            patch(
                "octop_harness.builtin.tools.desktop_screenshot._resolve_display",
                return_value=None,
            ),
        ):
            block = desktop_screenshot.invoke({"path": str(target)})

        assert block["type"] == "image"
        assert block["filename"] == "shot.png"
        assert block["path"] == str(target.absolute())
        assert target.is_file()

    def test_default_path_creates_tempfile(self) -> None:
        with (
            patch.dict("sys.modules", {"mss": self._fake_mss_module()}),
            patch(
                "octop_harness.builtin.tools.desktop_screenshot.shutil.which",
                return_value=None,
            ),
            patch(
                "octop_harness.builtin.tools.desktop_screenshot._resolve_display",
                return_value=None,
            ),
        ):
            block = desktop_screenshot.invoke({})

        assert block["filename"].endswith(".png")
        # Cleanup the temp file so we don't pollute /tmp.
        Path(block["path"]).unlink(missing_ok=True)

    def test_non_png_extension_normalized(self, tmp_path: Path) -> None:
        target = tmp_path / "noext"

        def _shot(*, mon: int, output: str) -> None:
            assert output.endswith(".png")
            Path(output).write_bytes(b"\x89PNG\r\n\x1a\n")

        with (
            patch.dict("sys.modules", {"mss": self._fake_mss_module(_shot)}),
            patch(
                "octop_harness.builtin.tools.desktop_screenshot.shutil.which",
                return_value=None,
            ),
            patch(
                "octop_harness.builtin.tools.desktop_screenshot._resolve_display",
                return_value=None,
            ),
        ):
            block = desktop_screenshot.invoke({"path": str(target)})
        assert block["path"].endswith(".png")

    def test_workspace_default_writes_outbound_screenshots(self, tmp_path: Path) -> None:
        ws = self._workspace(tmp_path)
        tool = build_desktop_screenshot_tool(ws)

        with (
            patch.dict("sys.modules", {"mss": self._fake_mss_module()}),
            patch(
                "octop_harness.builtin.tools.desktop_screenshot.shutil.which",
                return_value=None,
            ),
            patch(
                "octop_harness.builtin.tools.desktop_screenshot._resolve_display",
                return_value=None,
            ),
        ):
            block = tool.invoke({})

        assert block["path"].startswith(f"{DEFAULT_SCREENSHOTS_DIR}/")
        saved = tmp_path / block["path"]
        assert saved.is_file()
        assert saved.parent == tmp_path / DEFAULT_SCREENSHOTS_DIR

    def test_workspace_creates_missing_parent_dirs(self, tmp_path: Path) -> None:
        ws = self._workspace(tmp_path)
        tool = build_desktop_screenshot_tool(ws)

        with (
            patch.dict("sys.modules", {"mss": self._fake_mss_module()}),
            patch(
                "octop_harness.builtin.tools.desktop_screenshot.shutil.which",
                return_value=None,
            ),
            patch(
                "octop_harness.builtin.tools.desktop_screenshot._resolve_display",
                return_value=None,
            ),
        ):
            block = tool.invoke({"path": "temp/screenshot.png"})

        # Basename is forced under outbound/screenshots for media delivery.
        expected = tmp_path / DEFAULT_SCREENSHOTS_DIR / "screenshot.png"
        assert expected.is_file()
        assert block["path"] == f"{DEFAULT_SCREENSHOTS_DIR}/screenshot.png"

    def test_workspace_remaps_external_absolute_path(self, tmp_path: Path) -> None:
        ws = self._workspace(tmp_path)
        tool = build_desktop_screenshot_tool(ws)
        outside = Path("/tmp/octop_desktop_shot_outside.png")

        with (
            patch.dict("sys.modules", {"mss": self._fake_mss_module()}),
            patch(
                "octop_harness.builtin.tools.desktop_screenshot.shutil.which",
                return_value=None,
            ),
            patch(
                "octop_harness.builtin.tools.desktop_screenshot._resolve_display",
                return_value=None,
            ),
        ):
            block = tool.invoke({"path": str(outside)})

        expected = tmp_path / DEFAULT_SCREENSHOTS_DIR / "octop_desktop_shot_outside.png"
        assert expected.is_file()
        assert block["path"] == f"{DEFAULT_SCREENSHOTS_DIR}/octop_desktop_shot_outside.png"

    def test_workspace_filename_lands_in_outbound_screenshots(self, tmp_path: Path) -> None:
        ws = self._workspace(tmp_path)
        tool = build_desktop_screenshot_tool(ws)

        with (
            patch.dict("sys.modules", {"mss": self._fake_mss_module()}),
            patch(
                "octop_harness.builtin.tools.desktop_screenshot.shutil.which",
                return_value=None,
            ),
            patch(
                "octop_harness.builtin.tools.desktop_screenshot._resolve_display",
                return_value=None,
            ),
        ):
            block = tool.invoke({"path": "screenshot.png"})

        expected = tmp_path / DEFAULT_SCREENSHOTS_DIR / "screenshot.png"
        assert expected.is_file()
        assert block["path"] == f"{DEFAULT_SCREENSHOTS_DIR}/screenshot.png"

    def test_missing_mss_returns_error(self, tmp_path: Path) -> None:
        # Force the import to fail by hiding ``mss`` from sys.modules and
        # making any fresh import attempt error out. Also hide ImageMagick
        # so the virtual-display fallback cannot mask the missing package.
        target = tmp_path / "shot.png"
        with (
            patch.dict("sys.modules", {"mss": None}),
            patch(
                "octop_harness.builtin.tools.desktop_screenshot.shutil.which",
                return_value=None,
            ),
            patch(
                "octop_harness.builtin.tools.desktop_screenshot._resolve_display",
                return_value=None,
            ),
        ):
            result = desktop_screenshot.invoke({"path": str(target)})
        assert isinstance(result, str)
        assert result.startswith("Error:")
        assert "mss" in result

    def test_imagemagick_fallback_on_virtual_display(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        target = tmp_path / "vnc.png"
        monkeypatch.setenv("DISPLAY", ":99")

        def _fake_run(cmd: list[str], **_: object) -> object:
            assert "import" in cmd[0]
            assert "-window" in cmd
            Path(cmd[-1]).write_bytes(b"\x89PNG\r\n\x1a\n")
            result = MagicMock()
            result.returncode = 0
            result.stderr = ""
            result.stdout = ""
            return result

        with (
            patch(
                "octop_harness.builtin.tools.desktop_screenshot.shutil.which",
                return_value="/usr/bin/import",
            ),
            patch(
                "octop_harness.builtin.tools.desktop_screenshot.subprocess.run",
                side_effect=_fake_run,
            ),
            patch(
                "octop_harness.builtin.tools.desktop_screenshot.platform.system",
                return_value="Linux",
            ),
        ):
            block = desktop_screenshot.invoke({"path": str(target)})
        assert block["type"] == "image"
        assert target.is_file()

    def test_mss_prefers_xlib_backend_with_display(self, tmp_path: Path) -> None:
        import importlib

        # Prefer importlib: ``import …desktop_screenshot as mod`` can resolve to the
        # StructuredTool re-exported on ``octop_harness.builtin.tools``.
        mod = importlib.import_module("octop_harness.builtin.tools.desktop_screenshot")

        target = tmp_path / "shot.png"
        seen_backends: list[str] = []

        class _FakeMss:
            def __init__(self, *, backend: str = "default", display: str | None = None) -> None:
                seen_backends.append(backend)
                assert display == ":99"
                if backend != "xlib":
                    raise RuntimeError(f"backend {backend} unavailable")

            def shot(self, *, mon: int, output: str) -> None:
                Path(output).write_bytes(b"\x89PNG\r\n\x1a\n")

            def close(self) -> None:
                """No-op."""

        fake_mss = MagicMock()
        fake_mss.MSS = _FakeMss
        with patch.dict("sys.modules", {"mss": fake_mss}):
            mod._capture_mss(str(target), ":99")
        assert target.is_file()
        assert seen_backends[0] == "xlib"

    @pytest.mark.skipif(
        platform.system() != "Darwin",
        reason="capture_window=True only triggers screencapture on macOS",
    )
    def test_macos_window_capture_invokes_screencapture(self, tmp_path: Path) -> None:
        target = tmp_path / "win.png"

        def _fake_run(cmd: list[str], **_: object) -> object:
            assert cmd[0] == "screencapture"
            assert "-w" in cmd
            assert cmd[-1] == str(target)
            target.write_bytes(b"\x89PNG\r\n\x1a\n")
            result = MagicMock()
            result.returncode = 0
            result.stderr = ""
            return result

        with patch(
            "octop_harness.builtin.tools.desktop_screenshot.subprocess.run",
            side_effect=_fake_run,
        ):
            block = desktop_screenshot.invoke({"path": str(target), "capture_window": True})
        assert block["type"] == "image"
