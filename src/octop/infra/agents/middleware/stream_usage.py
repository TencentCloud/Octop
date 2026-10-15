"""Normalize cumulative OpenAI-compatible stream usage before it is persisted."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.callbacks.base import BaseCallbackManager
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.messages.ai import UsageMetadata
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, GenerationChunk, LLMResult
from langchain_openai.chat_models.base import BaseChatOpenAI


@dataclass
class _UsageSamples:
    latest: UsageMetadata
    count: int = 1
    cumulative: bool = True


class _CumulativeUsageCallback(BaseCallbackHandler):
    # Finish normalization before the model result reaches context accounting.
    run_inline = True

    def __init__(self) -> None:
        self._runs: dict[UUID, _UsageSamples] = {}

    def on_llm_new_token(
        self,
        token: str | list[str | dict[str, Any]],
        *,
        run_id: UUID,
        chunk: GenerationChunk | ChatGenerationChunk | None = None,
        **kwargs: Any,
    ) -> None:
        if not isinstance(chunk, ChatGenerationChunk) or not isinstance(
            chunk.message, AIMessageChunk
        ):
            return
        usage = chunk.message.usage_metadata
        if not usage or not (usage["input_tokens"] or usage["output_tokens"]):
            return
        previous = self._runs.get(run_id)
        if previous is None:
            self._runs[run_id] = _UsageSamples(
                latest=deepcopy(usage), cumulative=usage["input_tokens"] > 0
            )
            return
        previous.cumulative = (
            previous.cumulative
            and usage["input_tokens"] == previous.latest["input_tokens"]
            and usage["output_tokens"] >= previous.latest["output_tokens"]
        )
        previous.latest = deepcopy(usage)
        previous.count += 1

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        samples = self._runs.pop(run_id, None)
        if samples is None or samples.count < 2 or not samples.cumulative:
            return
        if len(response.generations) != 1 or len(response.generations[0]) != 1:
            return
        generation = response.generations[0][0]
        if not isinstance(generation, ChatGeneration) or not isinstance(
            generation.message, AIMessage
        ):
            return
        message = generation.message
        usage = message.usage_metadata
        # Only undo the exact repeated-prompt sum. Standard terminal-only usage,
        # delta usage and already-normalized model results are left intact.
        if usage and usage["input_tokens"] == samples.latest["input_tokens"] * samples.count:
            message.usage_metadata = samples.latest

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._runs.pop(run_id, None)


def _with_usage_callback(request: ModelRequest[Any]) -> ModelRequest[Any]:
    model = request.model
    if not isinstance(model, BaseChatOpenAI):
        return request
    callback = _CumulativeUsageCallback()
    callbacks = model.callbacks
    if isinstance(callbacks, BaseCallbackManager):
        callbacks = callbacks.copy()
        callbacks.add_handler(callback)
    else:
        callbacks = [*(callbacks or []), callback]
    # Factories cache models across concurrent turns; never mutate their callbacks.
    return request.override(model=model.model_copy(update={"callbacks": callbacks}))


class StreamUsageMiddleware(AgentMiddleware[Any, Any]):
    """Keep repeated cumulative usage out of snapshots, history and compaction.

    Some compatible endpoints repeat full prompt usage on every SSE chunk.
    LangChain adds those chunks together. Its final model callback lets us
    restore the last cumulative sample before harness captures the response,
    without changing the individual usage events consumed by the live UI.
    """

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        return handler(_with_usage_callback(request))

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        return await handler(_with_usage_callback(request))
