"""Unit tests for TLS certificate storage and config updates."""

from __future__ import annotations

import json
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


def test_merge_config_file_keeps_previous_config_when_swap_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crash while merging the TLS section must not truncate config.json.

    ``config.json`` holds the database settings (including credentials) and is
    written in place, so an interrupted write left a truncated file that every
    later start refused as "not valid JSON". It is now swapped in via
    ``write_json_atomic``, so a failing swap keeps the previous file.
    """
    import os

    config_path = tmp_path / "config.json"
    previous = json.dumps({"database": {"driver": "sqlite", "sqlite_path": "octop.db"}}, indent=2)
    previous += "\n"
    config_path.write_text(previous, encoding="utf-8")

    def _fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated swap failure")

    monkeypatch.setattr(os, "replace", _fail)
    with pytest.raises(OSError, match="simulated swap failure"):
        _merge_config_file(config_path, {"port": 443})

    assert config_path.read_text(encoding="utf-8") == previous
