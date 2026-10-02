"""Compatibility fixes for supported octop-harness releases."""

from __future__ import annotations

from typing import Any, cast


def normalize_stream_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
            continue
        if not isinstance(block, dict):
            continue

        block_type = block.get("type")
        if block_type in {"thinking", "reasoning"}:
            text = block.get("thinking") or block.get("reasoning") or block.get("text")
            if isinstance(text, str) and text:
                parts.extend(("<think>", text, "</think>"))
            continue

        text = block.get("text")
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


def install_stream_content_compat() -> None:
    from octop_harness.protocols.think_splitter import ThinkSplitter

    feed = ThinkSplitter.feed
    if getattr(feed, "_octop_content_blocks_compat", False):
        return

    def compatible_feed(self: Any, content: Any) -> tuple[str, str]:
        return feed(self, normalize_stream_content(content))

    compatible_feed.__dict__["_octop_content_blocks_compat"] = True
    type.__setattr__(ThinkSplitter, "feed", cast(Any, compatible_feed))
