"""Internal MCP URL must follow the HTTPS API listener, not the HTTP companion."""

from __future__ import annotations

import asyncio
import json

import httpx

from octop.config import OctopConfig, TlsConfig
from octop.infra.connectors.builder import (
    _redact_mcp_configs_for_log,
    build_http_mcp_spec,
    internal_mcp_url,
)
from octop.infra.connectors.catalog import get_catalog_entry


def _qcc_spec(config: OctopConfig) -> dict[str, object]:
    entry = get_catalog_entry("qcc")
    assert entry is not None
    return build_http_mcp_spec(
        entry=entry,
        instance_id="qcc-test",
        creds={"access_token": "tok", "internal_token": "local-gateway-token"},
        config=config,
    )


def test_internal_mcp_url_uses_http_when_tls_is_off() -> None:
    url = internal_mcp_url(
        config=OctopConfig(),
        gateway_kind="qcc",
        instance_id="qcc-test",
        internal_token="tok",
    )
    assert url.startswith("http://127.0.0.1:8088/api/internal/mcp/qcc/qcc-test?")
    spec = _qcc_spec(OctopConfig())
    assert str(spec["url"]).startswith("http://")
    assert "httpx_client_factory" not in spec


def test_internal_mcp_url_uses_https_when_tls_is_enabled() -> None:
    config = OctopConfig(
        bind_host="0.0.0.0",
        port=443,
        tls=TlsConfig(enabled=True, cert_file="ssl/fullchain.pem", key_file="ssl/privkey.pem"),
    )
    url = internal_mcp_url(
        config=config,
        gateway_kind="qcc",
        instance_id="qcc-test",
        internal_token="tok",
    )
    assert url.startswith("https://127.0.0.1:443/api/internal/mcp/qcc/qcc-test?")
    spec = _qcc_spec(config)
    assert str(spec["url"]).startswith("https://127.0.0.1:443/")
    factory = spec["httpx_client_factory"]
    assert callable(factory)
    client = factory()
    assert isinstance(client, httpx.AsyncClient)
    asyncio.run(client.aclose())


def test_internal_mcp_url_stays_http_when_tls_enabled_without_certs() -> None:
    config = OctopConfig(tls=TlsConfig(enabled=True))
    url = internal_mcp_url(
        config=config,
        gateway_kind="qcc",
        instance_id="qcc-test",
        internal_token="tok",
    )
    assert url.startswith("http://")


def test_tls_internal_mcp_spec_is_json_loggable() -> None:
    config = OctopConfig(
        tls=TlsConfig(enabled=True, cert_file="ssl/fullchain.pem", key_file="ssl/privkey.pem"),
    )
    spec = _qcc_spec(config)
    assert callable(spec["httpx_client_factory"])
    payload = json.dumps(_redact_mcp_configs_for_log({"qcc__x": spec}), ensure_ascii=False)
    assert "https://" in payload
    assert "httpx_client_factory" in payload
    assert "<callable" in payload
