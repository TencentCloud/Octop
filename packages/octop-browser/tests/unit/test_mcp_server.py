"""Import-time smoke tests for the MCP server entry point.

``mcp_server`` is the only module that imports ``mcp``, and it registers its
handlers with the low-level ``@app.list_tools()`` / ``@app.call_tool()``
decorators *at import time*. Those decorators were removed in mcp 2.x, so an
unconstrained ``mcp`` dependency makes ``python -m octop_browser.mcp_server``
fail immediately with ``AttributeError: 'Server' object has no attribute
'list_tools'``.

Nothing else in the package imports ``mcp``, so without these tests a broken
MCP entry point stays invisible to the rest of the suite.
"""

from __future__ import annotations

import importlib
import importlib.metadata as md
import re


def _release(version: str) -> tuple[int, ...]:
    """Parse the numeric release part of a version, ignoring pre/post suffixes."""
    head = re.split(r"[^0-9.]", version, maxsplit=1)[0].rstrip(".")
    return tuple(int(part) for part in head.split("."))


def test_mcp_version_is_within_supported_range() -> None:
    """Guard the ``mcp>=1.9,<2`` floor/ceiling declared in pyproject.toml."""
    raw = md.version("mcp")
    installed = _release(raw)
    assert (1, 9) <= installed < (2,), (
        f"mcp {raw} is outside the supported range (>=1.9,<2); "
        "the low-level Server decorator API differs outside it"
    )


def test_mcp_server_module_imports() -> None:
    """The module must import cleanly — decorators run at import time."""
    mod = importlib.import_module("octop_browser.mcp_server")
    assert mod.app.name == "octop-browser"


async def test_list_tools_returns_registered_tools() -> None:
    mod = importlib.import_module("octop_browser.mcp_server")
    tools = await mod.list_tools()
    names = {t.name for t in tools}

    assert len(tools) >= 20
    # One representative per family: core action, tab control, record, install.
    for expected in (
        "browser_navigate",
        "browser_click",
        "browser_dom_tree",
        "browser_list_tabs",
        "browser_record_start",
        "install_browser",
    ):
        assert expected in names

    # Every tool needs a usable JSON schema, otherwise clients reject it.
    for tool in tools:
        assert tool.description
        assert tool.inputSchema.get("type") == "object"


async def test_close_session_tool_is_exposed_with_kill_flag() -> None:
    """MCP clients must be able to release the browser, not just detach."""
    mod = importlib.import_module("octop_browser.mcp_server")
    tools = {t.name: t for t in await mod.list_tools()}

    assert "browser_close_session" in tools
    props = tools["browser_close_session"].inputSchema["properties"]
    assert props["kill"]["type"] == "boolean"
    assert props["kill"]["default"] is False
    assert mod._ACTION_MAP["browser_close_session"] == "close_session"


def test_action_map_targets_exist_on_tool_interface() -> None:
    """Every mapped MCP tool must resolve to a real browser_tool action."""
    mod = importlib.import_module("octop_browser.mcp_server")
    tool_names = {t.name for t in mod._TOOLS}

    for tool_name in mod._ACTION_MAP:
        assert tool_name in tool_names, f"{tool_name} is mapped but not exposed"
