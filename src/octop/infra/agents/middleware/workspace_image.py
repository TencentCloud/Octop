"""Ephemeral vision-image preparation for model calls (plan B).

Checkpoint / history keep path-only ``workspace://`` refs or the original
inline bytes. This middleware expands refs and fits images that exceed the
vision byte or edge caps onto the model request only, so base64 and resized
copies never land in LangGraph state or the dashboard history payload.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

from octop.infra.gateway.media.attachment_hints import (
    expand_workspace_image_ref,
    expand_workspace_image_ref_sync,
    fit_inline_image_block,
    is_workspace_image_ref,
)

if TYPE_CHECKING:
    from octop_harness.backends.workspace import BackendWorkspace


def _same_blocks(prepared: Sequence[Any], original: Sequence[Any]) -> bool:
    """True when preparation returned each block object unchanged."""
    pairs = zip(prepared, original, strict=True)
    return all(new is old for new, old in pairs)


def _is_inline_data_image(block: object) -> bool:
    if not isinstance(block, dict):
        return False
    if str(block.get("type") or "") not in {"image", "image_url", "input_image"}:
        return False
    url_field = block.get("image_url")
    url = url_field.get("url") if isinstance(url_field, dict) else url_field
    return isinstance(url, str) and url.startswith("data:")


class WorkspaceImageMaterializeMiddleware(AgentMiddleware[Any, Any]):
    """Expand ``workspace://`` refs and fit oversized images before the provider call."""

    def __init__(self, *, workspace: BackendWorkspace) -> None:
        self._workspace = workspace

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        messages = self._expand_messages_sync(request.messages)
        return handler(request.override(messages=messages))

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        messages = await self._expand_messages(request.messages)
        return await handler(request.override(messages=messages))

    def _prepare_block_sync(self, block: Any) -> Any:
        if isinstance(block, dict) and is_workspace_image_ref(block):
            return expand_workspace_image_ref_sync(block, workspace=self._workspace)
        if isinstance(block, dict):
            return fit_inline_image_block(block)
        return block

    async def _prepare_block(self, block: Any) -> Any:
        if isinstance(block, dict) and is_workspace_image_ref(block):
            return await expand_workspace_image_ref(block, workspace=self._workspace)
        # Pillow only for an inline data image; text blocks stay on the event loop.
        if _is_inline_data_image(block):
            return await asyncio.to_thread(fit_inline_image_block, block)
        return block

    def _expand_messages_sync(self, messages: Sequence[Any]) -> list[Any]:
        out: list[Any] = []
        for msg in messages:
            content = getattr(msg, "content", None)
            if not isinstance(content, list):
                out.append(msg)
                continue
            new_blocks = [self._prepare_block_sync(block) for block in content]
            if _same_blocks(new_blocks, content):
                out.append(msg)
                continue
            out.append(msg.model_copy(update={"content": new_blocks}))
        return out

    async def _expand_messages(self, messages: Sequence[Any]) -> list[Any]:
        out: list[Any] = []
        for msg in messages:
            content = getattr(msg, "content", None)
            if not isinstance(content, list):
                out.append(msg)
                continue
            new_blocks = [await self._prepare_block(block) for block in content]
            if _same_blocks(new_blocks, content):
                out.append(msg)
                continue
            out.append(msg.model_copy(update={"content": new_blocks}))
        return out


__all__ = ["WorkspaceImageMaterializeMiddleware"]
