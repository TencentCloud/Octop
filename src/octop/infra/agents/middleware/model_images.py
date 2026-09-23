"""Save model-generated images before checkpoints and publish attachment events."""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.exceptions import ModelError
from langchain_core.messages import AIMessage
from langgraph.config import get_stream_writer

from octop.config import DEFAULT_MAX_UPLOAD_MB, upload_mb_to_bytes
from octop.infra.agents.providers.image_output import (
    IMAGE_EVENT,
    IMAGES_KEY,
    RAW_IMAGES_KEY,
    with_image_output,
)

if TYPE_CHECKING:
    from harness_agent.backends.workspace import BackendWorkspace

_IMAGE_EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/avif": "avif",
    "image/bmp": "bmp",
}
_MAX_BYTES = upload_mb_to_bytes(DEFAULT_MAX_UPLOAD_MB)


def _image_reference(url: str) -> tuple[dict[str, Any], bytes | None]:
    if not url.startswith("data:"):
        if urlsplit(url).scheme not in {"http", "https"}:
            raise ValueError("Unsupported model image URL scheme")
        # Keep remote references without making server-side requests to model URLs.
        return {"type": "image_url", "image_url": {"url": url}}, None
    header, _, payload = url.partition(",")
    mime = header[5:].removesuffix(";base64").lower()
    if not header.endswith(";base64") or mime not in _IMAGE_EXTENSIONS:
        raise ValueError("Unsupported model image data URI")
    if len(payload) > 4 * ((_MAX_BYTES + 2) // 3):
        raise ValueError("Model image exceeds the upload limit")
    raw = base64.b64decode(payload, validate=True)
    if not raw or len(raw) > _MAX_BYTES:
        raise ValueError("Model image is empty or exceeds the upload limit")
    filename = f"{hashlib.sha256(raw).hexdigest()}.{_IMAGE_EXTENSIONS[mime]}"
    path = f"outbound/generated/{filename}"
    return {
        "type": "image_url",
        "image_url": {"url": f"workspace://{path}"},
        "workspace_path": path,
        "filename": filename,
        "mime_type": mime,
    }, raw


def _request_with_images(request: ModelRequest[Any]) -> ModelRequest[Any]:
    messages = []
    for message in request.messages:
        images = message.additional_kwargs.get(IMAGES_KEY)
        if isinstance(message, AIMessage) and images:
            # The provider's assistant input schema is text-only. Keep a small
            # reference for follow-up questions, never resend generated base64.
            refs = [image["image_url"]["url"] for image in images]
            content = f"{message.text}\n[Generated images: {', '.join(refs)}]".strip()
            message = message.model_copy(update={"content": content})
        messages.append(message)
    return request.override(model=with_image_output(request.model), messages=messages)


def _publish(message: AIMessage, images: list[dict[str, Any]]) -> None:
    message.additional_kwargs.pop(RAW_IMAGES_KEY, None)
    if (
        not (message.content.strip() if isinstance(message.content, str) else message.content)
        and not message.tool_calls
        and not images
    ):
        # Reject before graph state/history sees an invisible AI message.
        # ModelError is non-retryable: don't bill another completed request.
        raise ModelError("EmptyModelResponse: no content, images or tool calls")
    if images:
        message.additional_kwargs[IMAGES_KEY] = images
        writer = get_stream_writer()
        for image in images:
            writer({"type": IMAGE_EVENT, "image": image})


class ModelImagesMiddleware(AgentMiddleware[Any, Any]):
    def __init__(self, *, workspace: BackendWorkspace) -> None:
        self._workspace = workspace

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        response = handler(_request_with_images(request))
        for message in response.result:
            if not isinstance(message, AIMessage):
                continue
            images = []
            for url in dict.fromkeys(message.additional_kwargs.get(RAW_IMAGES_KEY, [])):
                image, raw = _image_reference(url)
                if raw is not None:
                    self._workspace.upload_bytes(image["workspace_path"], raw)
                images.append(image)
            _publish(message, images)
        return response

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        response = await handler(_request_with_images(request))
        for message in response.result:
            if not isinstance(message, AIMessage):
                continue
            images = []
            for url in dict.fromkeys(message.additional_kwargs.get(RAW_IMAGES_KEY, [])):
                image, raw = _image_reference(url)
                if raw is not None:
                    await self._workspace.aupload_bytes(image["workspace_path"], raw)
                images.append(image)
            _publish(message, images)
        return response
