"""Unit tests for TLS certificate storage and config updates."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from octop.config import TlsConfig, load_config
from octop.infra.setup.tls.store import (
    _merge_config_file,
    install_letsencrypt_cert,
    resolve_tls_paths,
)
from octop.infra.utils.paths import PathLayout


def test_install_letsencrypt_cert_updates_config(tmp_path: Path):
    paths = PathLayout(tmp_path)
    paths.ensure_root()
    load_config(paths.config)

    install_letsencrypt_cert(
        paths,
        domain="octop.example.com",
        cert_pem=b"-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----\n",
        key_pem=b"-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
        expires_at="2030-01-01T00:00:00+00:00",
        acme_staging=True,
    )

    raw = json.loads(paths.config.read_text(encoding="utf-8"))
    assert raw["bind_host"] == "0.0.0.0"
    assert raw["port"] == 443
    assert raw["tls"]["enabled"] is True
    assert raw["tls"]["domains"] == ["octop.example.com"]
    assert raw["tls"]["http_port"] == 80
    assert (paths.ssl_dir / "fullchain.pem").is_file()
    assert (paths.ssl_dir / "privkey.pem").is_file()

    cfg = load_config(paths.config)
    cert, key = resolve_tls_paths(paths.root, cfg.tls)
    assert cert is not None
    assert key is not None


def test_resolve_tls_paths_when_disabled():
    cert, key = resolve_tls_paths(Path("/tmp"), TlsConfig(enabled=False))
    assert cert is None
    assert key is None


def test_merge_config_file_keeps_previous_config_when_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A failed config write must not truncate the existing ``config.json``.

    ``load_config`` raises on a corrupt file and refuses to start the server, so
    an interrupted merge (killed process, full disk) that leaves a partial write
    behind would brick the next boot.
    """
    config_path = tmp_path / "config.json"
    original = {"database": {"url": "sqlite:///keep-me.db"}, "port": 8080}
    config_path.write_text(json.dumps(original), encoding="utf-8")

    real_replace = os.replace

    def boom(src, dst):
        raise OSError("simulated crash before the rename")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        _merge_config_file(config_path, {"port": 443})
    monkeypatch.setattr(os, "replace", real_replace)

    assert json.loads(config_path.read_text(encoding="utf-8")) == original
