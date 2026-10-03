"""Persist TLS certificates and merge config.json."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from octop.config import TlsConfig
from octop.infra.setup.tls.listeners import TLS_HTTP_PORT, TLS_HTTPS_PORT
from octop.infra.utils.paths import PathLayout

REL_CERT_FILE = "ssl/fullchain.pem"
REL_KEY_FILE = "ssl/privkey.pem"


def resolve_tls_paths(root: Path, tls: TlsConfig) -> tuple[str | None, str | None]:
    """Return absolute cert/key paths when TLS is enabled and files exist."""
    if not tls.enabled or not tls.cert_file or not tls.key_file:
        return None, None
    cert = Path(tls.cert_file)
    key = Path(tls.key_file)
    if not cert.is_absolute():
        cert = root / cert
    if not key.is_absolute():
        key = root / key
    if cert.is_file() and key.is_file():
        return str(cert), str(key)
    return None, None


def main_service_scheme(tls: TlsConfig, root: Path | None = None) -> str:
    """Return the scheme the main port actually serves: ``https`` under TLS.

    Mirrors ``launch.run_foreground``: the main listener gets the SSL config
    exactly when ``resolve_tls_paths`` resolves both files. Callers build
    loopback URLs (internal MCP, probes) that must match that scheme.
    """
    if root is None:
        root = PathLayout.from_env().root
    cert, key = resolve_tls_paths(root, tls)
    return "https" if cert and key else "http"


def _atomic_write_bytes(path: Path, data: bytes, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_bytes(data)
    if mode is not None:
        os.chmod(tmp, mode)
    os.replace(tmp, path)


def _merge_config_file(config_path: Path, patch: dict[str, Any]) -> None:
    data: dict[str, Any] = {}
    if config_path.exists():
        data = json.loads(config_path.read_text(encoding="utf-8"))
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            merged = dict(data[key])
            merged.update(value)
            data[key] = merged
        else:
            data[key] = value
    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def install_letsencrypt_cert(
    paths: PathLayout,
    *,
    domain: str,
    cert_pem: bytes,
    key_pem: bytes,
    expires_at: str,
    acme_staging: bool,
) -> None:
    """Write certificate files and update config.json for HTTPS on port 443."""
    ssl_dir = paths.ensure_ssl_dir()
    cert_path = ssl_dir / "fullchain.pem"
    key_path = ssl_dir / "privkey.pem"
    _atomic_write_bytes(cert_path, cert_pem)
    _atomic_write_bytes(key_path, key_pem, mode=0o600)

    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    _merge_config_file(
        paths.config,
        {
            "bind_host": "0.0.0.0",
            "port": TLS_HTTPS_PORT,
            "tls": {
                "enabled": True,
                "mode": "letsencrypt",
                "domains": [domain],
                "cert_file": REL_CERT_FILE,
                "key_file": REL_KEY_FILE,
                "issued_at": now,
                "expires_at": expires_at,
                "acme_staging": acme_staging,
                "http_port": TLS_HTTP_PORT,
            },
        },
    )


def account_key_path(paths: PathLayout) -> Path:
    return paths.ssl_dir / "acme_account.key.pem"
