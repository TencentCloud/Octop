"""Ephemeral workspace-image rematerialization for model calls (plan B).

Checkpoint / history keep path-only ``image_url`` refs (``workspace://…``).
This middleware expands them to ``data:`` URIs on the model request only so
base64 never lands in LangGraph state or the dashboard history payload.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

from octop.infra.gateway.media.attachment_hints import (
    expand_workspace_image_ref,
    expand_workspace_image_ref_sync,
    is_workspace_image_ref,
)

if TYPE_CHECKING:
    from harness_agent.backends.workspace import BackendWorkspace


class WorkspaceImageMaterializeMiddleware(AgentMiddleware[Any, Any]):
    """Inline ``workspace://`` vision refs just before the provider call."""

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

    def _expand_messages_sync(self, messages: Sequence[Any]) -> list[Any]:
        out: list[Any] = []
        for msg in messages:
            content = getattr(msg, "content", None)
            if not isinstance(content, list) or not any(
                is_workspace_image_ref(block) for block in content if isinstance(block, dict)
            ):
                out.append(msg)
                continue
            new_blocks: list[Any] = [
                (
                    expand_workspace_image_ref_sync(block, workspace=self._workspace)
                    if isinstance(block, dict) and is_workspace_image_ref(block)
                    else block
                )
                for block in content
            ]
            out.append(msg.model_copy(update={"content": new_blocks}))
        return out

    async def _expand_messages(self, messages: Sequence[Any]) -> list[Any]:
        out: list[Any] = []
        for msg in messages:
            content = getattr(msg, "content", None)
            if not isinstance(content, list) or not any(
                is_workspace_image_ref(block) for block in content if isinstance(block, dict)
            ):
                out.append(msg)
                continue
            new_blocks: list[Any] = []
            for block in content:
                if isinstance(block, dict) and is_workspace_image_ref(block):
                    new_blocks.append(
                        await expand_workspace_image_ref(block, workspace=self._workspace)
                    )
                else:
                    new_blocks.append(block)
            out.append(msg.model_copy(update={"content": new_blocks}))
        return out


__all__ = ["WorkspaceImageMaterializeMiddleware"]
