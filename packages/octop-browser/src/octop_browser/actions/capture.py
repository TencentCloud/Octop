"""Screenshot capture action.

Writes a PNG file to disk and returns its path. We deliberately do **not**
return the raw base64 payload to callers — base64 strings are large and
costly to push through agent toolchains, and the file path is what
downstream renderers (file_preview, dashboards, MCP clients) need anyway.

Output location precedence:

1. Explicit ``path=`` argument (absolute → as-is, relative → under
   ``settings.screenshots_dir``)
2. ``settings.screenshots_dir / octop-<timestamp_ms>.png``

Optional flags:

- ``full_page=True`` — capture the entire scrollable page using
  ``Page.getLayoutMetrics().cssContentSize`` to size the clip rectangle.
  **Use sparingly.** Real-world pages scroll for many screens (10+ viewports
  is typical), so ``full_page`` PNGs are huge and rarely useful for agents
  trying to locate one element — prefer the viewport default plus targeted
  scrolling. ``full_page`` is appropriate only when the caller explicitly
  needs a single-image archival/regression capture.
- ``element_ref="..."`` — clip to one element's bounding box. Mutually
  exclusive with ``full_page`` (element_ref wins to keep behavior
  predictable).

The action also enriches ``ToolResult.metadata`` with the page ``url`` and
``title`` so the caller can surface them without an extra ``Runtime.evaluate``.
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

from octop_browser.cdp.client import CDPClient, CDPSessionError
from octop_browser.dom.refs import RefCache
from octop_browser.models import ActionMetrics, ToolResult
from octop_browser.settings import OctopSettings
from octop_browser.settings import settings as _default_settings


def _resolve_path(
    path: str | Path | None,
    cfg: OctopSettings,
) -> Path:
    """Compute the destination path for a screenshot."""
    base = Path(cfg.screenshots_dir)
    if path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = base / candidate
        candidate.parent.mkdir(parents=True, exist_ok=True)
        return candidate
    base.mkdir(parents=True, exist_ok=True)
    return base / f"octop-{int(time.time() * 1000)}.png"


async def _page_context(client: CDPClient) -> dict[str, str]:
    """Return ``{"url": ..., "title": ...}`` via a single Runtime.evaluate.

    Failures are non-fatal — we just return empty strings.
    """
    try:
        info = await client.send(
            "Runtime.evaluate",
            {
                "expression": (
                    "JSON.stringify({url: location.href, title: document.title})"
                ),
                "returnByValue": True,
            },
        )
        raw = info.get("result", {}).get("value", "{}")
        data = json.loads(raw) if isinstance(raw, str) else {}
        return {
            "url": str(data.get("url", "")),
            "title": str(data.get("title", "")),
        }
    except Exception:  # pylint: disable=broad-except
        return {"url": "", "title": ""}


async def screenshot(
    client: CDPClient,
    ref_cache: RefCache,
    crop: bool = False,
    element_ref: str | None = None,
    full_page: bool = False,
    path: str | Path | None = None,
    settings: OctopSettings | None = None,
) -> ToolResult:
    """Capture a screenshot, write it to disk, and return its path.

    Args:
        client: Connected CDP client for the active page.
        ref_cache: Ref cache for ``element_ref`` lookup.
        crop: Reserved for future use; currently has no independent effect.
        element_ref: If set, crop to the bounding box of this element ref.
            Takes precedence over ``full_page``.
        full_page: If True (and ``element_ref`` is unset), capture the full
            scrollable page, not just the visible viewport. **Default False
            — almost always leave it that way.** Modern landing pages
            routinely scroll for 10+ viewports; a ``full_page`` PNG is
            then several MB of mostly-empty visual noise that drowns
            agents in tokens. Reserve ``full_page=True`` for archival /
            visual-regression captures where a single image is the
            explicit deliverable.
        path: Optional output path. Absolute paths used verbatim; relative
            paths resolve under ``settings.screenshots_dir``.
        settings: :class:`OctopSettings` override. Defaults to the module
            singleton (env-driven).

    Returns:
        :class:`ToolResult` whose ``content`` is the absolute path string of
        the saved PNG. ``metadata`` carries ``{"url", "title", "full_page",
        "width", "height", "size_kb", "path"}`` so callers can render context
        without a follow-up CDP call.
    """
    cfg = settings or _default_settings
    start = time.monotonic()
    params: dict[str, Any] = {"format": "png"}

    width = 0
    height = 0

    if element_ref is not None:
        node_id = ref_cache.lookup(element_ref)
        if node_id is None:
            raise CDPSessionError(
                f"Ref '{element_ref}' not found. Call dom_tree() first."
            )
        box = await client.send("DOM.getBoxModel", {"nodeId": node_id})
        model = box.get("model", {})
        content_pts = model.get("content", [0, 0, 100, 0, 100, 100, 0, 100])
        x = min(content_pts[0::2])
        y = min(content_pts[1::2])
        width = max(content_pts[0::2]) - x
        height = max(content_pts[1::2]) - y
        params["clip"] = {
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "scale": 1,
        }
    elif full_page:
        # Use CSS content size so the clip captures the full scrollable page,
        # not just the current viewport. ``captureBeyondViewport`` lets Chrome
        # render outside the visible area into the PNG.
        metrics = await client.send("Page.getLayoutMetrics", {})
        # Newer CDP exposes cssContentSize / cssVisualViewport; fall back to
        # the older snake-cased fields if needed.
        css = metrics.get("cssContentSize") or metrics.get("contentSize") or {}
        width = int(css.get("width", 0)) or 0
        height = int(css.get("height", 0)) or 0
        if width > 0 and height > 0:
            params["clip"] = {
                "x": 0,
                "y": 0,
                "width": width,
                "height": height,
                "scale": 1,
            }
            params["captureBeyondViewport"] = True

    result = await client.send("Page.captureScreenshot", params)
    raw_b64: str = result.get("data", "")
    if not raw_b64:
        return ToolResult(
            success=False,
            content="",
            error="Page.captureScreenshot returned empty data",
            metrics=ActionMetrics(
                action="screenshot",
                duration_ms=int((time.monotonic() - start) * 1000),
                dom_nodes_scanned=0,
                estimated_tokens=0,
            ),
        )

    img_bytes = base64.b64decode(raw_b64)
    target = _resolve_path(path, cfg)
    target.write_bytes(img_bytes)

    # Default (viewport) capture leaves width/height at 0 above. Try to fill
    # them in from the visual viewport so callers can render a meaningful
    # size badge without a follow-up CDP call. Failures are non-fatal.
    if width == 0 and height == 0:
        try:
            metrics_resp = await client.send("Page.getLayoutMetrics", {})
            vp = (
                metrics_resp.get("cssVisualViewport")
                or metrics_resp.get("visualViewport")
                or {}
            )
            width = int(vp.get("clientWidth") or vp.get("width") or 0)
            height = int(vp.get("clientHeight") or vp.get("height") or 0)
        except Exception:  # pylint: disable=broad-except
            pass

    ctx = await _page_context(client)
    metadata: dict[str, object] = {
        "path": str(target),
        "url": ctx["url"],
        "title": ctx["title"],
        "full_page": bool(full_page and element_ref is None),
        "element_ref": element_ref,
        "width": width,
        "height": height,
        "size_kb": len(img_bytes) // 1024,
    }

    return ToolResult(
        success=True,
        content=str(target),
        metrics=ActionMetrics(
            action="screenshot",
            duration_ms=int((time.monotonic() - start) * 1000),
            dom_nodes_scanned=0,
            estimated_tokens=0,
            screenshot_size_kb=len(img_bytes) // 1024,
        ),
        metadata=metadata,
    )
