"""Pydantic models for octop-browser."""

from __future__ import annotations

from typing import Union

from pydantic import BaseModel


class ActionMetrics(BaseModel):
    """Per-action performance and token metrics."""

    action: str
    duration_ms: int
    dom_nodes_scanned: int
    estimated_tokens: int
    screenshot_size_kb: int = 0


class ToolResult(BaseModel):
    """Result returned by every BrowserSession method and browser_tool().

    ``metadata`` is an optional structured side-channel for action-specific
    context (e.g. screenshot returns its url/title/full_page flag here so
    ``content`` can stay a short path string instead of a verbose JSON blob).
    Callers that don't care about the side-channel can ignore it entirely.
    """

    success: bool
    content: Union[str, dict[str, object]]  # noqa: UP007
    error: str | None = None
    metrics: ActionMetrics
    metadata: dict[str, object] | None = None


class TabInfo(BaseModel):
    """Information about a browser tab."""

    tab_id: str
    url: str
    title: str
    active: bool
