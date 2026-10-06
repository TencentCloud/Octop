"""The TLS config file must never be left half written."""

from __future__ import annotations

import json
import os

import pytest

from octop.infra.setup.tls.store import _merge_config_file


def test_a_failed_merge_keeps_the_previous_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"tls": {"enabled": True}}) + "\n", encoding="utf-8")
    before = config_path.read_text(encoding="utf-8")

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", _boom)

    with pytest.raises(OSError):
        _merge_config_file(config_path, {"tls": {"port": 443}})

    # A truncating write would leave JSON the next merge cannot parse, so every
    # later TLS change would fail even though the certificate files were written.
    assert config_path.read_text(encoding="utf-8") == before
    assert list(tmp_path.glob("*.tmp")) == []


def test_the_merge_still_updates_the_config(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"tls": {"enabled": True}}) + "\n", encoding="utf-8")

    _merge_config_file(config_path, {"tls": {"port": 443}, "extra": 1})

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["tls"] == {"enabled": True, "port": 443}
    assert payload["extra"] == 1
