"""Interaction actions: click, type_text, scroll, hover."""

from __future__ import annotations

import time

from octop_browser.cdp.client import CDPClient, CDPSessionError
from octop_browser.dom.refs import RefCache
from octop_browser.models import ActionMetrics, ToolResult


def _metrics(action: str, start: float) -> ActionMetrics:
    return ActionMetrics(
        action=action,
        duration_ms=int((time.monotonic() - start) * 1000),
        dom_nodes_scanned=1,
        estimated_tokens=10,
    )


async def _get_center(client: CDPClient, node_id: int) -> tuple[float, float]:
    """Get the center coordinates of a DOM node."""
    box = await client.send("DOM.getBoxModel", {"nodeId": node_id})
    model = box.get("model", {})
    content = model.get("content", [0, 0, 0, 0, 0, 0, 0, 0])
    # content is [x0,y0, x1,y1, x2,y2, x3,y3] (clockwise from top-left)
    cx = (content[0] + content[4]) / 2
    cy = (content[1] + content[5]) / 2
    return cx, cy


async def _resolve_coords(
    client: CDPClient,
    ref_cache: RefCache,
    ref: str | None,
    selector: str | None,
    x: int | None,
    y: int | None,
) -> tuple[float, float, str]:
    """Resolve click target to (x, y, description)."""
    if ref is not None:
        node_id = ref_cache.lookup(ref)
        if node_id is None:
            raise CDPSessionError(f"Ref '{ref}' not found. Call dom_tree() first.")
        cx, cy = await _get_center(client, node_id)
        return cx, cy, f"ref={ref}"
    if selector is not None:
        doc = await client.send("DOM.getDocument", {"depth": 0})
        root_id = doc["root"]["nodeId"]
        result = await client.send(
            "DOM.querySelector", {"nodeId": root_id, "selector": selector}
        )
        node_id = result.get("nodeId", 0)
        if not node_id:
            raise CDPSessionError(f"Selector '{selector}' matched no elements.")
        cx, cy = await _get_center(client, node_id)
        return cx, cy, f"selector={selector}"
    if x is not None and y is not None:
        return float(x), float(y), f"({x}, {y})"
    raise ValueError("Must provide ref, selector, or (x, y)")


async def click(
    client: CDPClient,
    ref_cache: RefCache,
    ref: str | None = None,
    selector: str | None = None,
    x: int | None = None,
    y: int | None = None,
) -> ToolResult:
    """Click an element identified by ref, selector, or coordinates."""
    start = time.monotonic()
    cx, cy, desc = await _resolve_coords(client, ref_cache, ref, selector, x, y)
    for event_type in ("mousePressed", "mouseReleased"):
        await client.send(
            "Input.dispatchMouseEvent",
            {
                "type": event_type,
                "x": cx,
                "y": cy,
                "button": "left",
                "clickCount": 1,
            },
        )
    return ToolResult(
        success=True,
        content=f"Clicked {desc} at ({cx:.0f}, {cy:.0f})",
        metrics=_metrics("click", start),
    )


async def type_text(
    client: CDPClient,
    ref_cache: RefCache,
    text: str,
    ref: str | None = None,
    selector: str | None = None,
) -> ToolResult:
    """Type text, optionally clicking a target element first."""
    start = time.monotonic()
    if ref is not None or selector is not None:
        await click(client, ref_cache, ref=ref, selector=selector)
    for char in text:
        await client.send("Input.dispatchKeyEvent", {"type": "char", "text": char})
    return ToolResult(
        success=True,
        content=f"Typed {len(text)} character(s)",
        metrics=_metrics("type", start),
    )


async def scroll(
    client: CDPClient,
    ref_cache: RefCache,
    direction: str = "down",
    amount: int = 300,
) -> ToolResult:
    """Scroll the page in a direction by pixel amount."""
    start = time.monotonic()
    delta_y = amount if direction == "down" else -amount
    delta_x = (
        amount if direction == "right" else (-amount if direction == "left" else 0)
    )
    await client.send(
        "Input.dispatchMouseEvent",
        {
            "type": "mouseWheel",
            "x": 400,
            "y": 300,
            "deltaX": delta_x,
            "deltaY": delta_y,
        },
    )
    return ToolResult(
        success=True,
        content=f"Scrolled {direction} by {amount}px",
        metrics=_metrics("scroll", start),
    )


async def hover(
    client: CDPClient,
    ref_cache: RefCache,
    ref: str,
) -> ToolResult:
    """Move the mouse over an element."""
    start = time.monotonic()
    node_id = ref_cache.lookup(ref)
    if node_id is None:
        raise CDPSessionError(f"Ref '{ref}' not found. Call dom_tree() first.")
    cx, cy = await _get_center(client, node_id)
    await client.send(
        "Input.dispatchMouseEvent",
        {
            "type": "mouseMoved",
            "x": cx,
            "y": cy,
        },
    )
    return ToolResult(
        success=True,
        content=f"Hovered over ref={ref} at ({cx:.0f}, {cy:.0f})",
        metrics=_metrics("hover", start),
    )


async def fill_text(
    client: CDPClient,
    ref_cache: RefCache,
    text: str,
    ref: str | None = None,
    selector: str | None = None,
) -> ToolResult:
    """Replace the current field value with text."""
    start = time.monotonic()
    if ref is not None or selector is not None:
        await click(client, ref_cache, ref=ref, selector=selector)
    # Cross-platform select-all: send both Ctrl+A and Meta+A; Chrome ignores
    # the irrelevant modifier for the host platform in most editable controls.
    for modifiers in (2, 4):  # Ctrl, Meta
        await client.send(
            "Input.dispatchKeyEvent",
            {"type": "keyDown", "key": "a", "code": "KeyA", "modifiers": modifiers},
        )
        await client.send(
            "Input.dispatchKeyEvent",
            {"type": "keyUp", "key": "a", "code": "KeyA", "modifiers": modifiers},
        )
    await client.send(
        "Input.dispatchKeyEvent",
        {"type": "keyDown", "key": "Backspace", "code": "Backspace"},
    )
    await client.send(
        "Input.dispatchKeyEvent",
        {"type": "keyUp", "key": "Backspace", "code": "Backspace"},
    )
    for char in text:
        await client.send("Input.dispatchKeyEvent", {"type": "char", "text": char})
    return ToolResult(
        success=True,
        content=f"Filled {len(text)} character(s)",
        metrics=_metrics("fill", start),
    )


async def press_key(client: CDPClient, key: str) -> ToolResult:
    """Press a keyboard key such as Enter or Tab."""
    start = time.monotonic()
    code = {
        "Enter": "Enter",
        "Tab": "Tab",
        "Escape": "Escape",
        "Backspace": "Backspace",
    }.get(key, key)
    await client.send(
        "Input.dispatchKeyEvent", {"type": "keyDown", "key": key, "code": code}
    )
    await client.send(
        "Input.dispatchKeyEvent", {"type": "keyUp", "key": key, "code": code}
    )
    return ToolResult(
        success=True, content=f"Pressed {key}", metrics=_metrics("press", start)
    )


async def select_value(
    client: CDPClient,
    ref_cache: RefCache,
    value: str,
    ref: str | None = None,
    selector: str | None = None,
) -> ToolResult:
    """Set a select element value and dispatch input/change events."""
    start = time.monotonic()
    if ref is not None:
        node_id = ref_cache.lookup(ref)
        if node_id is None:
            raise CDPSessionError(f"Ref '{ref}' not found. Call dom_tree() first.")
        obj = await client.send("DOM.resolveNode", {"nodeId": node_id})
        object_id = obj.get("object", {}).get("objectId")
        if not object_id:
            raise CDPSessionError(f"Could not resolve ref '{ref}'.")
        expr = (
            "function(v){ this.value = v;"
            " this.dispatchEvent(new Event('input',{bubbles:true}));"
            " this.dispatchEvent(new Event('change',{bubbles:true}));"
            " return this.value; }"
        )
        await client.send(
            "Runtime.callFunctionOn",
            {
                "objectId": object_id,
                "functionDeclaration": expr,
                "arguments": [{"value": value}],
                "returnByValue": True,
            },
        )
    elif selector is not None:
        expression = (
            "(function(sel,v){const el=document.querySelector(sel); if(!el) throw new Error('selector not found');"
            "el.value=v;"
            " el.dispatchEvent(new Event('input',{bubbles:true}));"
            " el.dispatchEvent(new Event('change',{bubbles:true}));"
            " return el.value;})(" + repr(selector) + "," + repr(value) + ")"
        )
        await client.send(
            "Runtime.evaluate", {"expression": expression, "returnByValue": True}
        )
    else:
        raise ValueError("Must provide ref or selector")
    return ToolResult(
        success=True, content=f"Selected {value}", metrics=_metrics("select", start)
    )
