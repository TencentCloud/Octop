"""Tests for langchain-anthropic context_management stream patch."""

from __future__ import annotations

from unittest.mock import MagicMock

from octop.infra.agents.providers.anthropic_compat import (
    patch_langchain_anthropic_context_management,
)


def test_patch_adapts_dict_context_management() -> None:
    """Verify that a message_delta event with dict-shaped context_management does not crash."""
    patch_langchain_anthropic_context_management()

    from langchain_anthropic.chat_models import ChatAnthropic

    chat = ChatAnthropic(model="claude-3-7-sonnet-20250219", api_key="mock-key")

    # Construct an event mimicking what Anthropic API returns on final message_delta
    event = MagicMock()
    event.type = "message_delta"
    event.usage = MagicMock()
    event.usage.input_tokens = 10
    event.usage.output_tokens = 5
    event.usage.cache_creation_input_tokens = 0
    event.usage.cache_read_input_tokens = 0
    event.delta = MagicMock()
    event.delta.stop_reason = "end_turn"
    event.delta.stop_sequence = None
    event.delta.container = None
    # Crucial: context_management is a plain dict (no model_dump method)
    event.context_management = {"edits": []}

    # Calling _make_message_chunk_from_anthropic_event must succeed without AttributeError
    chunk, _ = chat._make_message_chunk_from_anthropic_event(
        event,
        stream_usage=True,
        coerce_content_to_string=False,
        block_start_event=None,
    )

    assert chunk is not None
    assert chunk.response_metadata.get("context_management") == {"edits": []}
    assert chunk.response_metadata.get("stop_reason") == "end_turn"
