"""MCP Server: expose browser_tool actions as MCP tools."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from octop_browser.install import install_chromium_stream
from octop_browser.record.daemon import ensure_daemon, send_request
from octop_browser.record.recorder import RecordController
from octop_browser.record.replay import ReplayRunner
from octop_browser.record.store import RecordingStore
from octop_browser.tool_interface import browser_tool

logger = logging.getLogger(__name__)

app = Server("octop-browser")

_TOOLS = [
    Tool(
        name="browser_navigate",
        description="Navigate browser to a URL",
        inputSchema={
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "profile": {"type": "string", "default": "default"},
            },
            "required": ["url"],
        },
    ),
    Tool(
        name="browser_dom_tree",
        description="Get page DOM tree (level: minimal/interactive/full/structured)",
        inputSchema={
            "type": "object",
            "properties": {
                "level": {
                    "type": "string",
                    "enum": ["minimal", "interactive", "full", "structured"],
                    "default": "interactive",
                },
                "profile": {"type": "string", "default": "default"},
            },
        },
    ),
    Tool(
        name="browser_screenshot",
        description=(
            "Capture a PNG screenshot. Writes to disk and returns the file "
            "path (not base64). Use full_page=true for the entire scrollable "
            "page; element_ref=<ref> for a single element."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "profile": {"type": "string", "default": "default"},
                "element_ref": {"type": "string"},
                "full_page": {"type": "boolean", "default": False},
                "path": {
                    "type": "string",
                    "description": (
                        "Optional output path. Absolute paths are used "
                        "verbatim; relative paths resolve under "
                        "BROWSER_USE_SCREENSHOTS_DIR."
                    ),
                },
            },
        },
    ),
    Tool(
        name="browser_click",
        description="Click an element by ref, selector, or coordinates",
        inputSchema={
            "type": "object",
            "properties": {
                "ref": {"type": "string"},
                "selector": {"type": "string"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "profile": {"type": "string", "default": "default"},
            },
        },
    ),
    Tool(
        name="browser_type",
        description="Type text into the page",
        inputSchema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "ref": {"type": "string"},
                "selector": {"type": "string"},
                "profile": {"type": "string", "default": "default"},
            },
            "required": ["text"],
        },
    ),
    Tool(
        name="browser_eval_js",
        description="Execute JavaScript in the page",
        inputSchema={
            "type": "object",
            "properties": {
                "expression": {"type": "string"},
                "profile": {"type": "string", "default": "default"},
            },
            "required": ["expression"],
        },
    ),
    Tool(
        name="browser_fill",
        description="Replace text in a field by ref or selector",
        inputSchema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "ref": {"type": "string"},
                "selector": {"type": "string"},
                "profile": {"type": "string", "default": "default"},
            },
            "required": ["text"],
        },
    ),
    Tool(
        name="browser_press",
        description="Press a keyboard key such as Enter or Tab",
        inputSchema={
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "profile": {"type": "string", "default": "default"},
            },
            "required": ["key"],
        },
    ),
    Tool(
        name="browser_wait",
        description="Wait for URL/text/selector condition",
        inputSchema={
            "type": "object",
            "properties": {
                "url_contains": {"type": "string"},
                "text": {"type": "string"},
                "selector": {"type": "string"},
                "timeout_ms": {"type": "integer", "default": 10000},
                "profile": {"type": "string", "default": "default"},
            },
        },
    ),
    Tool(
        name="browser_record_doctor",
        description="Check browser record/replay readiness",
        inputSchema={
            "type": "object",
            "properties": {"profile": {"type": "string", "default": "default"}},
        },
    ),
    Tool(
        name="browser_record_start",
        description="Start a daemon-backed browser recording",
        inputSchema={
            "type": "object",
            "properties": {
                "profile": {"type": "string", "default": "default"},
                "name": {"type": "string"},
                "privacy": {"type": "string", "default": "mask-sensitive"},
            },
        },
    ),
    Tool(
        name="browser_record_stop",
        description="Stop the active daemon-backed browser recording",
        inputSchema={
            "type": "object",
            "properties": {
                "recording_id": {"type": "string"},
                "name": {"type": "string"},
                "generate_steps": {"type": "boolean", "default": True},
            },
        },
    ),
    Tool(
        name="browser_record_status",
        description="Show active recording status",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="browser_record_list",
        description="List local browser recordings",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="browser_record_show",
        description="Show a recording's artifact paths and status",
        inputSchema={
            "type": "object",
            "properties": {"recording_id": {"type": "string"}},
            "required": ["recording_id"],
        },
    ),
    Tool(
        name="browser_record_generate_steps",
        description="Generate steps.json from a recording's events.jsonl",
        inputSchema={
            "type": "object",
            "properties": {"recording_id": {"type": "string"}},
            "required": ["recording_id"],
        },
    ),
    Tool(
        name="browser_record_generate_skill",
        description="Generate draft.skill.md from a recording's steps.json",
        inputSchema={
            "type": "object",
            "properties": {
                "recording_id": {"type": "string"},
                "name": {"type": "string"},
            },
            "required": ["recording_id"],
        },
    ),
    Tool(
        name="browser_replay_run",
        description="Replay a recorded workflow",
        inputSchema={
            "type": "object",
            "properties": {
                "recording_id": {"type": "string"},
                "profile": {"type": "string", "default": "default"},
                "inputs": {"type": "object"},
            },
            "required": ["recording_id"],
        },
    ),
    Tool(
        name="browser_new_tab",
        description="Open a new browser tab (optionally to a URL)",
        inputSchema={
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "profile": {"type": "string", "default": "default"},
            },
        },
    ),
    Tool(
        name="browser_switch_tab",
        description="Activate a browser tab by its id",
        inputSchema={
            "type": "object",
            "properties": {
                "tab_id": {"type": "string"},
                "profile": {"type": "string", "default": "default"},
            },
            "required": ["tab_id"],
        },
    ),
    Tool(
        name="browser_close_tab",
        description="Close a browser tab by its id",
        inputSchema={
            "type": "object",
            "properties": {
                "tab_id": {"type": "string"},
                "profile": {"type": "string", "default": "default"},
            },
        },
    ),
    Tool(
        name="browser_list_tabs",
        description="List all open browser tabs",
        inputSchema={
            "type": "object",
            "properties": {
                "profile": {"type": "string", "default": "default"},
            },
        },
    ),
    Tool(
        name="browser_close_session",
        description=(
            "Detach from the profile's CDP session. By default the Chrome "
            "process keeps running so later calls can re-attach; pass "
            "kill=true to also terminate the browser and free its port."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "profile": {"type": "string", "default": "default"},
                "kill": {
                    "type": "boolean",
                    "default": False,
                    "description": "Also terminate the Chrome process.",
                },
            },
        },
    ),
    Tool(
        name="browser_open",
        description=(
            "Launch a browser and open multiple URLs as separate tabs. "
            "If the browser is already running for the profile, attaches to it "
            "and opens each URL in a new tab. The first URL becomes the active tab. "
            "Use this instead of browser_navigate when you want to open several "
            "pages at once."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of URLs to open as tabs.",
                },
                "profile": {"type": "string", "default": "default"},
                "mode": {
                    "type": "string",
                    "enum": ["auto", "headed", "headless"],
                    "default": "auto",
                    "description": "Browser launch mode (only effective if not already running).",
                },
            },
            "required": ["urls"],
        },
    ),
    Tool(
        name="install_browser",
        description=(
            "Install a Playwright-managed Chromium binary into the standard "
            "Playwright cache (~/.cache/ms-playwright or "
            "$PLAYWRIGHT_BROWSERS_PATH). Idempotent: if a binary is already "
            "present, returns the existing path without re-downloading. "
            "Requires the `playwright` Python package to be installed in the "
            "current environment. Returns the aggregated installer log."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
]

_ACTION_MAP = {
    "browser_navigate": "navigate",
    "browser_dom_tree": "dom_tree",
    "browser_screenshot": "screenshot",
    "browser_click": "click",
    "browser_type": "type",
    "browser_eval_js": "eval_js",
    "browser_fill": "fill",
    "browser_press": "press",
    "browser_wait": "wait",
    "browser_new_tab": "new_tab",
    "browser_switch_tab": "switch_tab",
    "browser_close_tab": "close_tab",
    "browser_list_tabs": "list_tabs",
    "browser_close_session": "close_session",
}


@app.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
async def list_tools() -> list[Tool]:
    return _TOOLS


async def _handle_install_browser() -> list[TextContent]:
    """Run the Playwright Chromium installer and return its aggregated log."""
    log_lines: list[str] = []
    success = False
    error: str | None = None
    async for event in install_chromium_stream():
        if "log" in event:
            log_lines.append(event["log"])
        if event.get("done"):
            success = bool(event.get("success", False))
            err = event.get("error")
            if err:
                error = err

    summary = "OK" if success else f"FAILED{f': {error}' if error else ''}"
    body = "\n".join(log_lines) if log_lines else "(no output)"
    return [TextContent(type="text", text=f"{summary}\n\n{body}")]


@app.call_tool()  # type: ignore[untyped-decorator]
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "install_browser":
        return await _handle_install_browser()
    if name == "browser_record_doctor":
        data = await RecordController().doctor(
            profile=arguments.get("profile", "default")
        )
        return [TextContent(type="text", text=str(data))]
    if name == "browser_record_start":
        daemon = await ensure_daemon()
        data = (
            daemon
            if not daemon.get("ok")
            else await send_request(
                {
                    "command": "start",
                    "profile": arguments.get("profile", "default"),
                    "name": arguments.get("name"),
                    "privacy": arguments.get("privacy", "mask-sensitive"),
                }
            )
        )
        return [TextContent(type="text", text=str(data))]
    if name == "browser_record_stop":
        data = await send_request(
            {
                "command": "stop",
                "recording_id": arguments.get("recording_id"),
                "name": arguments.get("name"),
                "generate_steps": arguments.get("generate_steps", True),
            }
        )
        return [TextContent(type="text", text=str(data))]
    if name == "browser_record_status":
        data = await send_request({"command": "status"})
        return [TextContent(type="text", text=str(data))]
    if name == "browser_record_list":
        data = {
            "ok": True,
            "recordings": [
                m.model_dump(mode="json", by_alias=True)
                for m in RecordingStore().list_recordings()
            ],
        }
        return [TextContent(type="text", text=str(data))]
    if name == "browser_record_show":
        data = {
            "ok": True,
            **RecordingStore().recording_summary(str(arguments["recording_id"])),
        }
        return [TextContent(type="text", text=str(data))]
    if name == "browser_record_generate_steps":
        data = RecordController().generate_steps(str(arguments["recording_id"]))
        return [TextContent(type="text", text=str(data))]
    if name == "browser_record_generate_skill":
        data = RecordController().generate_skill(
            str(arguments["recording_id"]), skill_name=arguments.get("name")
        )
        return [TextContent(type="text", text=str(data))]
    if name == "browser_replay_run":
        data = await ReplayRunner().run(
            str(arguments["recording_id"]),
            profile=arguments.get("profile", "default"),
            inputs=arguments.get("inputs") or {},
        )
        return [TextContent(type="text", text=str(data))]

    action = _ACTION_MAP.get(name)
    if action is None:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    # Handle browser_open specially: it uses the urls parameter to create
    # a session with multiple tabs, then returns a summary of opened tabs.
    if name == "browser_open":
        urls = arguments.get("urls", [])
        mode = arguments.get("mode")
        profile = arguments.get("profile", "default")
        result = await browser_tool(
            action="list_tabs",
            profile=profile,
            urls=urls,
            mode=mode,
        )
    else:
        result = await browser_tool(action=action, **arguments)
    text = result.content if isinstance(result.content, str) else str(result.content)
    if not result.success:
        text = f"ERROR: {result.error}"
    return [TextContent(type="text", text=text)]


async def _main() -> None:
    """Start the MCP server.

    By default runs in stdio mode (for local CLI / agent integration).
    If the ``MCP_PORT`` environment variable is set, runs as an SSE HTTP
    server on that port (useful for remote / network access).
    """
    import os

    mcp_port = os.environ.get("MCP_PORT")
    if mcp_port:
        import uvicorn
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Route

        port = int(mcp_port)
        host = os.environ.get("MCP_HOST", "0.0.0.0")

        sse = SseServerTransport("/messages/")

        async def handle_sse(request: Any) -> Any:
            async with sse.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                await app.run(
                    streams[0],
                    streams[1],
                    app.create_initialization_options(),
                )

        starlette_app = Starlette(
            routes=[
                Route("/sse", endpoint=handle_sse),
                Route("/messages/", endpoint=sse.handle_post_message, methods=["POST"]),
            ],
        )

        config = uvicorn.Config(
            app=starlette_app, host=host, port=port, log_level="info"
        )
        server = uvicorn.Server(config)
        logger.info("Starting MCP SSE server on %s:%d", host, port)
        await server.serve()
    else:
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream, write_stream, app.create_initialization_options()
            )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())
