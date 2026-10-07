"""The COS manifest must never be left half written."""

from __future__ import annotations

import json
import os

import pytest

from octop.infra.agents.providers.onnx_download import write_cos_manifest


def test_a_failed_publish_keeps_the_previous_manifest(tmp_path, monkeypatch):
    (tmp_path / "model.onnx").write_bytes(b"weights")
    dest = write_cos_manifest(tmp_path, model_id="m", hf_repo="r")
    before = dest.read_text(encoding="utf-8")

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", _boom)

    with pytest.raises(OSError):
        write_cos_manifest(tmp_path, model_id="m2", hf_repo="r2")

    # A truncating write would leave JSON the upload path cannot parse.
    assert dest.read_text(encoding="utf-8") == before
    assert list(tmp_path.glob("*.tmp")) == []


def test_the_manifest_lists_the_model_files(tmp_path):
    (tmp_path / "model.onnx").write_bytes(b"weights")

    dest = write_cos_manifest(tmp_path, model_id="m", hf_repo="r")

    payload = json.loads(dest.read_text(encoding="utf-8"))
    assert payload["files"] == ["model.onnx"]
    assert payload["model_id"] == "m"
