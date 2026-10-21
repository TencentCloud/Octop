"""The TLS config file must never be left half written."""

from __future__ import annotations

import json
import os
import stat

import pytest

from octop.infra.setup.tls.store import _merge_config_file

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX file modes only")


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

    monkeypatch.undo()
    _merge_config_file(config_path, {"tls": {"port": 443}})
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["tls"] == {"enabled": True, "port": 443}


def test_the_merge_still_updates_the_config(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"tls": {"enabled": True}}) + "\n", encoding="utf-8")

    _merge_config_file(config_path, {"tls": {"port": 443}, "extra": 1})

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["tls"] == {"enabled": True, "port": 443}
    assert payload["extra"] == 1


@posix_only
def test_the_merge_keeps_the_config_file_mode(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"tls": {"enabled": True}}) + "\n", encoding="utf-8")
    os.chmod(config_path, 0o600)

    _merge_config_file(config_path, {"tls": {"port": 443}})

    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
