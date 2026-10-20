# pylint: disable=invalid-name
"""Custom provider example: OpenAI-compatible endpoint with multiple models
including automatic multimodal switching.

The auto-router picks the multimodal model when an image is attached.

Reads model config from environment variables (or ``.env``):

    OPENAI_API_KEY            - required
    OPENAI_BASE_URL           - defaults to ``https://api.openai.com/v1``
    OPENAI_MODEL_NAME         - text-only model (defaults to ``gpt-4o-mini``)
    OPENAI_VISION_MODEL_NAME  - multimodal model (defaults to
                                ``OPENAI_MODEL_NAME`` if unset, in which case
                                the router has only one model to pick from)

Run with::

    uv run python examples/02_custom_provider.py
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from octop_harness import (
    ChatRequest,
    HarnessAgentConfig,
    HarnessAgentManager,
    ModelConfig,
    ProviderConfig,
)

_DEMO_IMAGE_URL = (
    "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/"
    "PNG_transparency_demonstration_1.png/240px-PNG_transparency_demonstration_1.png"
)


async def main() -> None:
    load_dotenv()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required.")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    text_model_id = os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini")
    vision_model_id = os.environ.get("OPENAI_VISION_MODEL_NAME", text_model_id)

    models = [ModelConfig(id=text_model_id, input=["text"])]
    # Only register a separate multimodal model when the env vars actually
    # describe two different ids; otherwise the text model handles both
    # (and the router falls back to it gracefully).
    if vision_model_id != text_model_id:
        models.append(ModelConfig(id=vision_model_id, input=["text", "image"]))

    root = Path("./agent_root").absolute()
    config = HarnessAgentConfig(
        workspace_dir=root,
        name="multimodal-agent",
        # Sandbox the filesystem to the demo dir so the agent's grep/ls tools
        # don't recurse into ``/`` on the default ``local_shell`` backend.
        backend={"type": "filesystem", "root_dir": str(root), "virtual_mode": True},
        providers=[
            ProviderConfig(
                id="p",
                base_url=base_url,
                api_key=api_key,
                name="OpenAI-compatible",
                models=models,
            ),
        ],
        default_model=f"p/{text_model_id}",
        # multimodal_model is omitted — the router auto-detects the model
        # whose ``input`` includes ``image``.
        # Skip Memory + JSONL session log for this short demo so the
        # ``memory_search`` tool doesn't reach for an empty sqlite store.
        memory_enabled=False,
        session_log_enabled=False,
    )

    manager = HarnessAgentManager()
    entry = manager.create_agent(config)

    # Pure text → uses the text model. The "from your own training" framing
    # discourages the model from chasing ``web_fetch`` calls — handy for
    # demos against models prone to look up unknown brand names online.
    print("\n--- Text query ---")
    request = ChatRequest(
        messages="From your own training, in one sentence: what is octop-harness (no web search)?",
        thread_id="custom-provider-demo",
    )
    async for chunk in manager.stream(entry.agent_id, request):
        content = getattr(chunk, "content", None) or str(chunk)
        print(content, end="", flush=True)
    print()

    # Multimodal input → router auto-switches to the vision model when one
    # is configured. Skip it when the env only provides a text model — the
    # demo would otherwise feed an image URL to a text-only model and the
    # agent would chase ``web_fetch`` calls instead of "describing" it.
    if vision_model_id == text_model_id:
        print("(skipping multimodal scenario — set OPENAI_VISION_MODEL_NAME to a vision-capable model to enable it)")
        return
    req = ChatRequest(
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe the image."},
                    {
                        "type": "image_url",
                        "image_url": _DEMO_IMAGE_URL,
                    },
                ],
            },
        ],
        thread_id="multimodal-demo",
    )
    print("\n--- Multimodal query ---")
    async for chunk in manager.stream(entry.agent_id, req):
        content = getattr(chunk, "content", None) or str(chunk)
        print(content, end="", flush=True)
    print()


if __name__ == "__main__":
    asyncio.run(main())
