"""Native capture reuses workspace attachment storage without Agent/plugin changes."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from octop.infra.desktop import native_capture


def test_default_helper_path_matches_standalone_component(monkeypatch):
    monkeypatch.delenv("OCTOP_NATIVE_CAPTURE_HELPER", raising=False)
    assert native_capture.helper_path() == (
        Path(__file__).parents[2] / "native/capture/OctopCapture.app/Contents/MacOS/OctopCapture"
    )


@pytest.fixture
def capture_env(tmp_path, monkeypatch):
    helper = tmp_path / "helper"
    helper.touch()
    monkeypatch.setattr(native_capture.sys, "platform", "darwin")
    monkeypatch.setenv("OCTOP_NATIVE_CAPTURE_HELPER", str(helper))
    workspace = SimpleNamespace(
        workspace_dir=tmp_path / "workspace",
        backend=SimpleNamespace(root_dir=None),
        aexists=AsyncMock(return_value=False),
        aupload_bytes=AsyncMock(),
    )
    return workspace


@pytest.mark.parametrize("mode", ["scan", "photo", "album"])
async def test_original_and_preview_return_workspace_refs(capture_env, monkeypatch, mode):
    async def launch(executable, selected_mode, staging):
        assert selected_mode == mode
        Path(staging, "scan.pdf").write_bytes(b"%PDF-original")
        Path(staging, "preview.png").write_bytes(b"png-preview")
        Path(staging, "result.json").write_text(
            json.dumps(
                {"status": "ok", "files": ["scan.pdf"], "previews": {"scan.pdf": "preview.png"}}
            )
        )
        return SimpleNamespace(returncode=0, wait=AsyncMock(return_value=0))

    monkeypatch.setattr(native_capture.asyncio, "create_subprocess_exec", launch)
    result = await native_capture.capture_from_composer(capture_env, mode)
    assert result["status"] == "ok"
    stored = result["files"][0]
    assert stored["path"].startswith("inbound/")
    assert stored["preview_path"].startswith("inbound/")
    assert capture_env.aupload_bytes.await_count == 2


async def test_timeout_terminates_helper(capture_env, monkeypatch):
    process = SimpleNamespace(
        returncode=None,
        wait=AsyncMock(return_value=0),
        kill=lambda: setattr(process, "returncode", -9),
    )
    monkeypatch.setattr(
        native_capture.asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
    )

    async def timeout(awaitable, timeout):
        await awaitable
        raise TimeoutError

    monkeypatch.setattr(native_capture.asyncio, "wait_for", timeout)
    assert (await native_capture.capture_from_composer(capture_env))["status"] == "timeout"
    assert process.returncode == -9


async def test_busy_does_not_launch_another_ui(capture_env, monkeypatch):
    launch = AsyncMock()
    monkeypatch.setattr(native_capture.asyncio, "create_subprocess_exec", launch)
    async with native_capture._capture_lock:
        assert (await native_capture.capture_from_composer(capture_env))["status"] == "busy"
    launch.assert_not_called()


async def test_capture_respects_upload_limit(capture_env, monkeypatch):
    from octop.infra.errors import OctopError

    async def launch(*args):
        root = Path(args[2])
        (root / "scan.pdf").write_bytes(b"%PDF-too-large")
        (root / "result.json").write_text('{"status":"ok","files":["scan.pdf"]}')
        return SimpleNamespace(returncode=0, wait=AsyncMock(return_value=0))

    monkeypatch.setattr(native_capture.asyncio, "create_subprocess_exec", launch)
    with pytest.raises(OctopError):
        await native_capture.capture_from_composer(capture_env, max_bytes=1)
    capture_env.aupload_bytes.assert_not_called()


@pytest.mark.parametrize(
    "manifest",
    [
        "{",
        '{"status":"unknown"}',
        '{"status":"ok","files":["../secret"]}',
        '{"status":"ok","files":["missing.pdf"]}',
    ],
)
async def test_invalid_helper_output_is_error(capture_env, monkeypatch, manifest):
    async def launch(*args):
        Path(args[2], "result.json").write_text(manifest)
        return SimpleNamespace(returncode=0, wait=AsyncMock(return_value=0))

    monkeypatch.setattr(native_capture.asyncio, "create_subprocess_exec", launch)
    assert (await native_capture.capture_from_composer(capture_env))["status"] == "error"
    capture_env.aupload_bytes.assert_not_called()


def test_output_read_is_capped_before_upload(tmp_path):
    report = tmp_path / "report.pdf"
    report.write_bytes(b"x" * 100)
    assert len(native_capture._read_output(report, 10)) == 11
