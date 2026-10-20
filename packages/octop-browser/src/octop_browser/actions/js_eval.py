"""JavaScript evaluation action."""

from __future__ import annotations

import json
import time

from octop_browser.cdp.client import CDPClient
from octop_browser.models import ActionMetrics, ToolResult


async def eval_js(client: CDPClient, expression: str) -> ToolResult:
    """
    Execute a JavaScript expression in the page context.

    Returns the serialized result as a JSON string in content.
    """
    start = time.monotonic()
    result = await client.send(
        "Runtime.evaluate",
        {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        },
    )
    value = result.get("result", {})
    if value.get("subtype") == "error":
        description = value.get("description", "Unknown JS error")
        return ToolResult(
            success=False,
            content="",
            error=description,
            metrics=ActionMetrics(
                action="eval_js",
                duration_ms=int((time.monotonic() - start) * 1000),
                dom_nodes_scanned=0,
                estimated_tokens=0,
            ),
        )
    raw = value.get("value")
    content: str | dict[str, object]
    if isinstance(raw, dict):
        content = raw
    elif isinstance(raw, list):
        content = json.dumps(raw, ensure_ascii=False)
    else:
        content = json.dumps(raw, ensure_ascii=False) if raw is not None else "null"
    tokens = len(str(content)) // 4
    return ToolResult(
        success=True,
        content=content,
        metrics=ActionMetrics(
            action="eval_js",
            duration_ms=int((time.monotonic() - start) * 1000),
            dom_nodes_scanned=0,
            estimated_tokens=tokens,
        ),
    )
