"""Tencent Docs table tools must survive the remote MCP allowlist."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.tools import StructuredTool
from octop_harness.mcp import aload_mcp_tools

from octop.config import OctopConfig
from octop.infra.connectors.builder import build_http_mcp_spec, mcp_server_name
from octop.infra.connectors.catalog import get_catalog_entry


@pytest.mark.parametrize(
    "table_tools",
    [
        ("sheet.get_sheet_info", "sheet.set_cell_value", "sheet.set_range_value"),
        (
            "smartsheet.list_tables",
            "smartsheet.list_fields",
            "smartsheet.add_fields",
            "smartsheet.list_records",
            "smartsheet.add_records",
            "smartsheet.update_records",
            "smartsheet.add_view",
        ),
    ],
    ids=["online-sheet", "smart-sheet"],
)
async def test_table_tools_reach_harness(table_tools: tuple[str, ...]) -> None:
    entry = get_catalog_entry("tencent-docs")
    assert entry is not None
    server = mcp_server_name(entry.kind, "test-instance")
    spec = build_http_mcp_spec(
        entry=entry,
        instance_id="test-instance",
        creds={"token": "test-token"},
        config=OctopConfig(),
    )
    expected = {
        *table_tools,
        "get_content",
        "query_space_node",
        "query_space_list",
        "smartcanvas.read",
    }

    def result() -> str:
        return "table data"

    remote_tools = [
        StructuredTool.from_function(
            result, name=f"{server}_{name}", description="Remote document tool"
        )
        for name in [*sorted(expected), "slide.delete_slide"]
    ]
    # Mock only the remote transport; exercise the catalog, spec builder and
    # harness's real exact-name filtering with instance-prefixed tool names.
    with patch("octop_harness.mcp.MultiServerMCPClient") as client:
        client.return_value.get_tools = AsyncMock(return_value=remote_tools)
        tools = await aload_mcp_tools({server: spec})

    assert {tool.name.removeprefix(f"{server}_") for tool in tools} == {
        name.replace(".", "_") for name in expected
    }
