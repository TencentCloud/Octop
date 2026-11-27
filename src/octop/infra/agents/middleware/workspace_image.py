"""Ephemeral vision-image preparation for model calls (plan B).

Checkpoint / history keep path-only ``workspace://`` refs or the original
inline bytes. This middleware expands refs and fits images that exceed the
vision byte or edge caps onto the model request only, so base64 and resized
copies never land in LangGraph state or the dashboard history payload.
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langgraph.errors import GraphBubbleUp
from octop_harness.middleware.runtime import current_configurable

from octop.i18n.domains.attachment import attachment_image_rejected
from octop.infra.gateway.media.attachment_hints import (
    expand_workspace_image_ref,
    expand_workspace_image_ref_sync,
    fit_inline_image_block,
    is_workspace_image_ref,
)
from octop.infra.utils.locale import Locale

if TYPE_CHECKING:
    from octop_harness.backends.workspace import BackendWorkspace

logger = logging.getLogger(__name__)

_VISION_BLOCK_TYPES = frozenset({"image", "image_url", "input_image"})
_PENDING_SANITIZE_CAP = 512
_IMAGE_INVALID_MARKERS = (
    "image_invalid",
    "invalid_image",
    "invalid_image_format",
    "invalid_image_url",
    "unsupported_image",
    "image data rejected by upstream",
    "invalid image data",
    "could not process image",
    "unable to download image",
    "invalid base64 image",
    "exterror code 1210",
    "code 11135",
)


def is_image_invalid_error(exc: BaseException) -> bool:
    """Return True when an exception chain indicates an HTTP 400 image rejection."""
    seen: set[int] = set()
    current: BaseException | None = exc
    has_400 = False
    has_marker = False
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        status = getattr(current, "status_code", None)
        body_text = str(getattr(current, "body", "") or "")
        combined = f"{current} {body_text}".lower()
        if (
            status == 400
            or type(current).__name__ == "BadRequestError"
            or "error code: 400" in combined
            or "http 400" in combined
        ):
            has_400 = True
        if any(marker in combined for marker in _IMAGE_INVALID_MARKERS):
            has_marker = True
        if has_400 and has_marker:
            return True
        nxt = current.__cause__
        if nxt is None and not current.__suppress_context__:
            nxt = current.__context__
        current = nxt
    return False


def _same_blocks(prepared: Sequence[Any], original: Sequence[Any]) -> bool:
    """True when preparation returned each block object unchanged."""
    pairs = zip(prepared, original, strict=True)
    return all(new is old for new, old in pairs)


def _is_vision_block(block: object) -> bool:
    return isinstance(block, dict) and str(block.get("type") or "") in _VISION_BLOCK_TYPES


def _is_inline_data_image(block: object) -> bool:
    if not _is_vision_block(block):
        return False
    assert isinstance(block, dict)
    url_field = block.get("image_url")
    url = url_field.get("url") if isinstance(url_field, dict) else url_field
    return isinstance(url, str) and url.startswith("data:")


def _extract_messages(state: Any) -> list[Any]:
    if state is None:
        return []
    if isinstance(state, dict):
        return list(state.get("messages", []) or [])
    return list(getattr(state, "messages", []) or [])


def _message_id(msg: Any) -> str:
    raw = msg.get("id") if isinstance(msg, dict) else getattr(msg, "id", None)
    return raw.strip() if isinstance(raw, str) else ""


def _replace_vision_blocks_in_message(msg: Any, *, placeholder: str) -> Any | None:
    content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
    if not isinstance(content, list):
        return None
    changed = False
    new_blocks: list[Any] = []
    for block in content:
        if _is_vision_block(block):
            new_blocks.append({"type": "text", "text": placeholder})
            changed = True
        else:
            new_blocks.append(block)
    if not changed:
        return None
    if isinstance(msg, dict):
        return {**msg, "content": new_blocks}
    return msg.model_copy(update={"content": new_blocks})


def _messages_have_vision_block(messages: Sequence[Any]) -> bool:
    for msg in messages:
        content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
        if isinstance(content, list) and any(_is_vision_block(block) for block in content):
            return True
    return False


def _strip_vision_blocks_from_messages(
    messages: Sequence[Any], *, placeholder: str
) -> tuple[list[Any], set[str]]:
    out: list[Any] = []
    stripped_ids: set[str] = set()
    for msg in messages:
        replaced = _replace_vision_blocks_in_message(msg, placeholder=placeholder)
        if replaced is None:
            out.append(msg)
            continue
        out.append(replaced)
        msg_id = _message_id(msg)
        if msg_id:
            stripped_ids.add(msg_id)
    return out, stripped_ids


class WorkspaceImageMaterializeMiddleware(AgentMiddleware[Any, Any]):
    """Expand ``workspace://`` refs, fit images, and recover from 400 image rejection."""

    def __init__(self, *, workspace: BackendWorkspace, locale: str | Locale = "en") -> None:
        super().__init__()
        self._workspace = workspace
        self._locale: str | Locale = locale
        self._pending_sanitize: OrderedDict[str, tuple[set[str], str]] = OrderedDict()

    @staticmethod
    def _configurable(*, request: Any = None, runtime: Any = None) -> dict[str, Any]:
        cfg = current_configurable(request)
        if cfg:
            return cfg
        if runtime is not None:
            runtime_cfg = getattr(runtime, "config", None)
            if isinstance(runtime_cfg, dict):
                inner = runtime_cfg.get("configurable")
                if isinstance(inner, dict):
                    return inner
            direct = getattr(runtime, "configurable", None)
            if isinstance(direct, dict):
                return direct
            context = getattr(runtime, "context", None)
            if isinstance(context, dict):
                return context
        return {}

    @staticmethod
    def _scope_key(configurable: dict[str, Any]) -> str:
        raw = configurable.get("thread_id")
        return raw.strip() if isinstance(raw, str) and raw.strip() else "__default__"

    def _resolve_locale(self, configurable: dict[str, Any]) -> str | Locale:
        raw = configurable.get("locale")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        return self._locale

    def _remember_pending_sanitize(
        self, scope_key: str, message_ids: set[str], placeholder: str
    ) -> None:
        if not message_ids:
            return
        existing = self._pending_sanitize.pop(scope_key, None)
        merged_ids = set(existing[0]) if existing is not None else set()
        merged_ids.update(message_ids)
        self._pending_sanitize[scope_key] = (merged_ids, placeholder)
        while len(self._pending_sanitize) > _PENDING_SANITIZE_CAP:
            self._pending_sanitize.popitem(last=False)

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        messages = self._expand_messages_sync(request.messages)
        try:
            return handler(request.override(messages=messages))
        except GraphBubbleUp:
            raise
        except Exception as exc:
            if not (is_image_invalid_error(exc) and _messages_have_vision_block(messages)):
                raise
            configurable = self._configurable(request=request)
            scope_key = self._scope_key(configurable)
            placeholder = attachment_image_rejected(self._resolve_locale(configurable))
            stripped_messages, stripped_ids = _strip_vision_blocks_from_messages(
                messages, placeholder=placeholder
            )
            logger.warning(
                "model rejected image input; retrying without images thread=%s "
                "stripped_messages=%d detail=%s",
                scope_key,
                len(stripped_ids),
                str(exc)[:300],
            )
            response = handler(request.override(messages=stripped_messages))
            self._remember_pending_sanitize(scope_key, stripped_ids, placeholder)
            return response

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        messages = await self._expand_messages(request.messages)
        try:
            return await handler(request.override(messages=messages))
        except GraphBubbleUp:
            raise
        except Exception as exc:
            if not (is_image_invalid_error(exc) and _messages_have_vision_block(messages)):
                raise
            configurable = self._configurable(request=request)
            scope_key = self._scope_key(configurable)
            placeholder = attachment_image_rejected(self._resolve_locale(configurable))
            stripped_messages, stripped_ids = _strip_vision_blocks_from_messages(
                messages, placeholder=placeholder
            )
            logger.warning(
                "model rejected image input; retrying without images thread=%s "
                "stripped_messages=%d detail=%s",
                scope_key,
                len(stripped_ids),
                str(exc)[:300],
            )
            response = await handler(request.override(messages=stripped_messages))
            self._remember_pending_sanitize(scope_key, stripped_ids, placeholder)
            return response

    def after_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        scope_key = self._scope_key(self._configurable(runtime=runtime))
        entry = self._pending_sanitize.pop(scope_key, None)
        if entry is None:
            return None
        pending_ids, placeholder = entry
        messages = _extract_messages(state)
        if not messages:
            return None
        updated: list[Any] = []
        for msg in messages:
            msg_id = _message_id(msg)
            if not msg_id or msg_id not in pending_ids:
                continue
            sanitized = _replace_vision_blocks_in_message(msg, placeholder=placeholder)
            if sanitized is not None:
                updated.append(sanitized)
        return {"messages": updated} if updated else None

    async def aafter_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        return self.after_model(state, runtime)

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


__all__ = ["WorkspaceImageMaterializeMiddleware", "is_image_invalid_error"]
