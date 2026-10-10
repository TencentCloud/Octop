"""Standalone component contract without hardware, Octop runtime, or private photos."""

import importlib.machinery
import importlib.util
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

CLI = Path(__file__).parents[2] / "native/capture/octop-capture"


def component():
    loader = importlib.machinery.SourceFileLoader("native_capture_cli", str(CLI))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.mark.parametrize("mode", ["scan", "photo", "album", "import"])
def test_standalone_files_and_manifest(tmp_path, monkeypatch, mode):
    module = component()
    monkeypatch.setattr(module.sys, "platform", "darwin")
    helper = tmp_path / "helper"
    helper.touch()

    def run(command, **kwargs):
        assert command[:2] == [str(helper), mode]
        root = Path(command[2])
        (root / "document.pdf").write_bytes(b"%PDF-original")
        (root / "preview.png").write_bytes(b"png-preview")
        (root / "result.json").write_text(
            json.dumps(
                {
                    "status": "ok",
                    "files": ["document.pdf"],
                    "previews": {"document.pdf": "preview.png"},
                }
            )
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", run)
    result = module.capture(mode, tmp_path / "captures", helper=helper)
    assert result["status"] == "ok"
    assert result["schema_version"] == 1
    file = result["files"][0]
    assert Path(file["path"]).read_bytes() == b"%PDF-original"
    assert Path(file["preview_path"]).read_bytes() == b"png-preview"
    assert file["media_type"] == "application/pdf"
    assert json.loads(Path(result["manifest_path"]).read_text()) == result
    second = module.capture(mode, tmp_path / "captures", helper=helper)
    assert second["directory"] != result["directory"]


def test_cancel_and_timeout_contract(tmp_path, monkeypatch):
    module = component()
    monkeypatch.setattr(module.sys, "platform", "darwin")
    helper = tmp_path / "helper"
    helper.touch()

    def cancel(command, **kwargs):
        Path(command[2], "result.json").write_text('{"status":"cancelled","files":[]}')
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", cancel)
    assert module.capture("scan", tmp_path, helper=helper)["status"] == "cancelled"

    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 1)

    monkeypatch.setattr(module.subprocess, "run", timeout)
    result = module.capture("scan", tmp_path, timeout=1, helper=helper)
    assert result["status"] == "timeout"
    assert result["files"] == []


def test_rejects_escaping_output(tmp_path):
    module = component()
    with pytest.raises(ValueError):
        module.checked_file(tmp_path, "../secret")


@pytest.mark.skipif(os.name != "posix", reason="Requires POSIX symlink support")
def test_rejects_symlink_output(tmp_path):
    module = component()
    target = tmp_path / "file"
    target.touch()
    (tmp_path / "link").symlink_to(target)
    with pytest.raises(ValueError):
        module.checked_file(tmp_path, "link")


def test_unavailable_does_not_create_output(tmp_path, monkeypatch):
    module = component()
    monkeypatch.setattr(module.sys, "platform", "linux")
    output = tmp_path / "captures"
    assert module.capture("scan", output)["status"] == "unavailable"
    assert not output.exists()


def test_helper_failure_persists_manifest(tmp_path, monkeypatch):
    module = component()
    monkeypatch.setattr(module.sys, "platform", "darwin")
    helper = tmp_path / "helper"
    helper.touch()
    monkeypatch.setattr(
        module.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1)
    )
    result = module.capture("scan", tmp_path, helper=helper)
    assert result["status"] == "error"
    assert json.loads(Path(result["manifest_path"]).read_text()) == result
