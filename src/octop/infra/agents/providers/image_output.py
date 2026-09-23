"""Preserve OpenAI-compatible ``message.images`` / ``delta.images`` output.

LangChain's Chat Completions parser drops this provider extension. Adapt a
request-local copy of the routed model, retaining harness reasoning support,
credentials, HTTP clients and model settings. Never patch the shared model.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_openai.chat_models.base import BaseChatOpenAI

RAW_IMAGES_KEY = "octop_model_image_urls"
IMAGES_KEY = "octop_model_images"
IMAGE_EVENT = "octop_model_image"


def _image_urls(message: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for image in message.get("images") or []:
        if not isinstance(image, dict):
            continue
        ref = image.get("image_url")
        url = ref.get("url") if isinstance(ref, dict) else ref
        if isinstance(url, str) and url and url not in urls:
            urls.append(url)
    return urls


@lru_cache(maxsize=8)
def _image_model_type(base: type[Any]) -> type[Any]:
    class ImageOutputModel(base):  # type: ignore[misc]
        def _convert_chunk_to_generation_chunk(
            self,
            chunk: dict[str, Any],
            default_chunk_class: type[Any],
            base_generation_info: dict[str, Any] | None,
        ) -> Any:
            result = super()._convert_chunk_to_generation_chunk(
                chunk, default_chunk_class, base_generation_info
            )
            choices = chunk.get("choices") or []
            if result is not None and choices:
                urls = _image_urls(choices[0].get("delta") or {})
                if urls:
                    result.message.additional_kwargs[RAW_IMAGES_KEY] = urls
            return result

        def _create_chat_result(
            self,
            response: Any,
            generation_info: dict[str, Any] | None = None,
        ) -> Any:
            result = super()._create_chat_result(response, generation_info)
            raw = response if isinstance(response, dict) else response.model_dump()
            for generation, choice in zip(result.generations, raw.get("choices", []), strict=False):
                urls = _image_urls(choice.get("message") or {})
                if urls:
                    generation.message.additional_kwargs[RAW_IMAGES_KEY] = urls
            return result

    return ImageOutputModel


def with_image_output(model: BaseChatModel) -> BaseChatModel:
    if not isinstance(model, BaseChatOpenAI):
        return model
    copy = model.model_copy()
    # A shallow copy preserves Pydantic private attributes and harness metadata.
    # The subclass only extends response parsing; it adds no fields or clients.
    copy.__class__ = _image_model_type(type(model))
    return copy


def project_image_event(chunk: dict[str, Any]) -> dict[str, Any]:
    """Project the middleware's custom event onto the existing attachment wire."""
    data = chunk.get("data")
    if chunk.get("type") != "custom" or not isinstance(data, dict):
        return chunk
    if data.get("type") != IMAGE_EVENT:
        return chunk
    image = data["image"]
    return {
        "type": "attachment",
        "source": "model",
        "kind": "image",
        "url": image["image_url"]["url"],
        "path": image.get("workspace_path"),
        "filename": image.get("filename", "image"),
        "mime_type": image.get("mime_type"),
    }
