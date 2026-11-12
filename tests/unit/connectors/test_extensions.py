"""Connector overrides dispatch by registration, independently of product names."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from octop.config import OctopConfig
from octop.infra.connectors import builder, extensions, probe
from octop.infra.connectors.catalog import get_catalog_entry
from octop.infra.connectors.extensions import ConnectorExtension


@pytest.mark.asyncio
async def test_connector_owned_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    from octop.api.routers import connectors

    original = get_catalog_entry("open-design")
    assert original is not None
    entry = replace(original, kind="test-stdio")
    prepared = {"command": "test-cli"}
    normalized = {**prepared, "args": [], "env": {}}
    spec = {"transport": "stdio", **normalized}
    result = {"ok": True, "tool_count": 1}
    runtime = object()
    extension = ConnectorExtension(
        normalize_credentials=Mock(return_value=normalized),
        prepare_credentials=AsyncMock(return_value=prepared),
        connection_spec=Mock(return_value=spec),
        probe=AsyncMock(return_value=result),
        create_stdio_runtime=Mock(return_value=runtime),
    )
    # Bundled dispatch can select an implementation without changing any caller.
    monkeypatch.setattr(extensions, "_MODULES", {entry.kind: "test_connector"})
    monkeypatch.setattr(
        extensions,
        "import_module",
        lambda name: SimpleNamespace(connector_extension=lambda: extension),
    )
    monkeypatch.setattr(builder, "get_catalog_entry", lambda kind: entry)
    monkeypatch.setattr(connectors, "get_catalog_entry", lambda kind: entry)

    assert (
        await connectors._prepare_credentials(entry.kind, {"auto_detect": True}, None) == normalized
    )
    extension.prepare_credentials.assert_awaited_once_with({"auto_detect": True})
    extension.normalize_credentials.assert_called_once_with(prepared)
    assert (
        builder.build_http_mcp_spec(
            entry=entry, instance_id="test", creds=normalized, config=OctopConfig()
        )
        == spec
    )
    assert (
        await probe.probe_connector(entry, normalized, instance_id="test", config=OctopConfig())
        == result
    )
    assert builder.create_stdio_runtime(entry.kind, None, None) is runtime


def test_unregistered_stdio_uses_standard_runtime() -> None:
    from octop.infra.connectors.stdio import StdioRuntime

    assert extensions.get_connector_extension("custom-mcp") is None
    assert type(builder.create_stdio_runtime("custom-mcp", None, None)) is StdioRuntime
