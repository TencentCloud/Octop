"""Tests for stream_errors i18n domain."""

from __future__ import annotations

from octop.i18n.domains.stream import (
    MODEL_CALL_FAILED,
    RECURSION_LIMIT,
    STREAM_STALL,
    classify_stream_error_message,
    format_stream_error,
    stream_error_message,
)


def test_classify_stream_stall_from_minimax_timeout() -> None:
    msg = (
        "Model call failed after 3 attempts with StreamChunkTimeoutError: "
        "No streaming chunk received for 120.0s (model=MiniMax-M2.7, chunks_received=122). "
        "The connection may be alive at the TCP layer but is not producing content."
    )
    assert classify_stream_error_message(msg) == STREAM_STALL


def test_classify_stream_stall_prefers_inner_timeout() -> None:
    msg = "Agent error: No streaming chunk received for 60.0s (model=x, chunks_received=0)"
    assert classify_stream_error_message(msg) == STREAM_STALL


def test_classify_rate_limit() -> None:
    assert (
        classify_stream_error_message("Error code: 429 - {'error': {'type': 'rate_limit_error'}}")
        == "octop:stream_errors.rate_limit"
    )


def test_classify_auth() -> None:
    assert (
        classify_stream_error_message("Error code: 401 - Incorrect API key provided")
        == "octop:stream_errors.auth"
    )


def test_classify_context_length() -> None:
    assert (
        classify_stream_error_message(
            "Error code: 400 - This model's maximum context length is 128000 tokens"
        )
        == "octop:stream_errors.context_length"
    )


def test_classify_recursion_limit() -> None:
    msg = (
        "Recursion limit of 2 reached without hitting a stop condition. "
        "You can increase the limit by setting the `recursion_limit` config key.\n"
        "For troubleshooting, visit: "
        "https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT"
    )
    assert classify_stream_error_message(msg) == RECURSION_LIMIT
    assert (
        classify_stream_error_message("GraphRecursionError: GRAPH_RECURSION_LIMIT")
        == RECURSION_LIMIT
    )


def test_classify_model_call_failed_fallback() -> None:
    assert (
        classify_stream_error_message("Model call failed after 3 attempts with RuntimeError: boom")
        == MODEL_CALL_FAILED
    )


def test_classify_unknown_passthrough() -> None:
    assert classify_stream_error_message("disk full") is None


def test_format_stream_error_zh_guidance() -> None:
    msg = (
        "Model call failed after 3 attempts with StreamChunkTimeoutError: "
        "No streaming chunk received for 120.0s"
    )
    text = format_stream_error(msg, "zh")
    assert "重试" in text
    assert "StreamChunkTimeoutError" not in text
    assert "LANGCHAIN" not in text


def test_format_recursion_limit_zh_guides_to_config() -> None:
    msg = (
        "Recursion limit of 2 reached without hitting a stop condition. "
        "You can increase the limit by setting the `recursion_limit` config key."
    )
    text = format_stream_error(msg, "zh")
    assert "运行配置" in text
    assert "最大迭代次数" in text
    assert "GRAPH_RECURSION_LIMIT" not in text
    assert "recursion_limit" not in text


def test_stream_error_message_octop_key() -> None:
    assert "重试" in stream_error_message(STREAM_STALL, "zh")


def test_format_stream_error_unknown_falls_back_to_localized() -> None:
    text = format_stream_error("disk full", "en")
    assert "disk full" not in text
    assert "model call failed" in text
