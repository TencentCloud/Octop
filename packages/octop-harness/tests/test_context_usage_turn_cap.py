"""Tests for ContextUsageMiddleware turn-model cap."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from langchain.agents.middleware import ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from octop_harness.context_usage import CONTEXT_USAGE_KEY
from octop_harness.middleware.context_usage import ContextUsageMiddleware


def test_capture_uses_request_model_profile_window() -> None:
    mw = ContextUsageMiddleware(max_tokens=128_000)
    request = MagicMock()
    request.system_message = SystemMessage(content="sys")
    request.system_prompt = None
    request.tools = []
    request.messages = [HumanMessage(content="hello world")]
    request.runtime = None
    request.model = MagicMock(profile={"max_input_tokens": 131_072})

    ai = AIMessage(
        content="ok",
        usage_metadata={"input_tokens": 50, "output_tokens": 2, "total_tokens": 52},
    )
    response = ModelResponse(result=[ai])

    with patch(
        "octop_harness.middleware.context_usage._thread_id_from_request",
        return_value="thr_1",
    ):
        out = mw._capture(request, response)

    stamped = out.result[0]
    payload = stamped.additional_kwargs[CONTEXT_USAGE_KEY]
    assert payload["max_tokens"] == 131_072
    snap = mw.get_snapshot("thr_1")
    assert snap is not None
    assert snap.max_tokens == 131_072
