from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda

from octop.infra.agents.middleware.siliconflow_usage import (
    SiliconFlowUsageMiddleware,
    is_siliconflow_model,
    strip_stream_usage,
)


def test_detects_siliconflow_base_url() -> None:
    assert is_siliconflow_model(SimpleNamespace(base_url="https://api.siliconflow.cn/v1"))
    assert not is_siliconflow_model(SimpleNamespace(base_url="https://api.deepseek.com/v1"))


def test_strips_inflated_usage_but_preserves_response_metadata() -> None:
    message = AIMessage(
        content="answer",
        usage_metadata={"input_tokens": 671_670, "output_tokens": 34, "total_tokens": 671_704},
        response_metadata={
            "model_name": "deepseek-ai/DeepSeek-V4-Flash",
            "token_usage": {"prompt_tokens": 671_670},
            "finish_reason": "stop",
        },
    )

    sanitized = strip_stream_usage(message)

    assert sanitized.usage_metadata is None
    assert sanitized.response_metadata == {
        "model_name": "deepseek-ai/DeepSeek-V4-Flash",
        "finish_reason": "stop",
    }
    assert sanitized.content == message.content


def test_non_ai_messages_are_unchanged() -> None:
    message = HumanMessage(content="hello")
    assert strip_stream_usage(message) is message


def test_middleware_sanitizes_the_routed_model_response() -> None:
    model = RunnableLambda(
        lambda _input, **_kwargs: AIMessage(
            content="answer",
            usage_metadata={"input_tokens": 99, "output_tokens": 1, "total_tokens": 100},
        )
    )
    model.base_url = "https://api.siliconflow.cn/v1"
    request = SimpleNamespace(
        model=model,
        override=lambda **changes: SimpleNamespace(**{**vars(request), **changes}),
    )

    prepared = SiliconFlowUsageMiddleware()._prepare(request)

    assert prepared.model.invoke("hello").usage_metadata is None
