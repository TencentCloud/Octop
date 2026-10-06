"""The trash manifest is the only record of a skill's original slug."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "src/octop/infra/agents/builtin_skills/skill-manager/scripts/manage_skills.py"
)


def _module():
    spec = importlib.util.spec_from_file_location("manage_skills_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_failed_manifest_write_keeps_the_previous_one(tmp_path, monkeypatch):
    module = _module()
    manifest = tmp_path / ".skill-manager-trash.json"
    manifest.write_text(json.dumps({"slug": "old"}), encoding="utf-8")
    before = manifest.read_text(encoding="utf-8")

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", _boom)

    with pytest.raises(OSError):
        module._write_json_atomically(manifest, {"slug": "new"})

    # The trash directory name carries a -1 suffix when it collided, so this file
    # is the only record of the real slug: a partial write means the skill comes
    # back under the wrong name, or not at all once json.loads fails.
    assert manifest.read_text(encoding="utf-8") == before
    assert list(tmp_path.glob("*.tmp")) == []


def test_the_manifest_is_written(tmp_path):
    module = _module()
    manifest = tmp_path / ".skill-manager-trash.json"

    module._write_json_atomically(manifest, {"slug": "demo"})

    assert json.loads(manifest.read_text(encoding="utf-8")) == {"slug": "demo"}


def test_the_remove_path_no_longer_writes_the_manifest_directly():
    source = SCRIPT.read_text(encoding="utf-8")

    assert '".skill-manager-trash.json").write_text(' not in source
    assert "_write_json_atomically(destination / \".skill-manager-trash.json\"" in source
