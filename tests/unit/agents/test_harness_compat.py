from __future__ import annotations

from octop_harness.protocols.think_splitter import ThinkSplitter

from octop.infra.agents.harness_compat import (
    install_stream_content_compat,
    normalize_stream_content,
)


def test_normalize_stream_content_preserves_text_and_thinking_blocks() -> None:
    assert (
        normalize_stream_content(
            [
                {"type": "text", "text": "answer"},
                {"type": "thinking", "thinking": "reason"},
                " tail",
            ]
        )
        == "answer<think>reason</think> tail"
    )


def test_think_splitter_accepts_content_blocks() -> None:
    install_stream_content_compat()
    splitter = ThinkSplitter()

    final_text, thinking_text = splitter.feed(
        [
            {"type": "text", "text": "answer"},
            {"type": "reasoning", "text": "reason"},
        ]
    )

    assert final_text == "answer"
    assert thinking_text == "reason"
