"""ModelAccess — protocol-aware access to a bound chat model."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from typing import TYPE_CHECKING, Any

from langchain_core.messages import BaseMessage

from octop_harness.llm.invoke_helpers import bind_call_options, build_text_messages, stringify_content

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from octop_harness.protocols.base import ChatProtocol


class ModelAccess:
    """Access handle for one resolved ``provider/model`` ref.

    Obtain via :meth:`ChatModelFactory.get` / :meth:`ChatModelFactory.get_for`.
    All invoke/stream methods accept ``protocol`` (default ``"langgraph"``).
    """

    def __init__(
        self,
        *,
        model_ref: str,
        chat_model: BaseChatModel,
        get_protocol: Callable[[str | None], ChatProtocol],
    ) -> None:
        self._model_ref = model_ref
        self._chat_model = chat_model
        self._get_protocol = get_protocol

    @property
    def model_ref(self) -> str:
        return self._model_ref

    @property
    def chat_model(self) -> BaseChatModel:
        return self._chat_model

    def _protocol(self, name: str | None) -> ChatProtocol:
        return self._get_protocol(name)

    def invoke(
        self,
        messages: list[BaseMessage],
        *,
        protocol: str = "langgraph",
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        if config is not None:
            import asyncio

            return asyncio.get_event_loop().run_until_complete(
                self._protocol(protocol).call(messages, config, **kwargs),
            )
        response = self._chat_model.invoke(messages, config=config, **kwargs)
        return stringify_content(getattr(response, "content", response))

    async def ainvoke(
        self,
        messages: list[BaseMessage],
        *,
        protocol: str = "langgraph",
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        if config is not None:
            return await self._protocol(protocol).call(messages, config, **kwargs)
        response = await self._chat_model.ainvoke(messages, config=config, **kwargs)
        return stringify_content(getattr(response, "content", response))

    def stream(
        self,
        messages: list[BaseMessage],
        *,
        protocol: str = "langgraph",
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Iterator[Any]:
        import asyncio

        async def _collect() -> list[Any]:
            out: list[Any] = []
            async for chunk in self.astream(messages, protocol=protocol, config=config, **kwargs):
                out.append(chunk)
            return out

        yield from asyncio.get_event_loop().run_until_complete(_collect())

    async def astream(
        self,
        messages: list[BaseMessage],
        *,
        protocol: str = "langgraph",
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        if config is not None:
            async for event in self._protocol(protocol).stream(messages, config, **kwargs):
                yield event
            return
        async for part in self._chat_model.astream(messages, config=config, **kwargs):
            yield part

    async def stream_events(
        self,
        messages: list[BaseMessage],
        *,
        protocol: str = "langgraph",
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        return await self._protocol(protocol).stream_events(messages, config or {}, **kwargs)

    def _prepare_text_call(
        self,
        prompt: str,
        kwargs: dict[str, Any],
    ) -> tuple[Any, list[BaseMessage], dict[str, Any]]:
        """Pop single-turn text options; leftover kwargs go to the model call."""
        kwargs.pop("protocol", "langgraph")  # single-turn text always uses chat_model
        messages = build_text_messages(prompt, system=kwargs.pop("system", None))
        model = bind_call_options(
            self._chat_model,
            max_tokens=kwargs.pop("max_tokens", None),
            temperature=kwargs.pop("temperature", None),
            response_format=kwargs.pop("response_format", "text"),
            timeout_s=kwargs.pop("timeout_s", None),
        )
        return model, messages, kwargs

    def invoke_text(self, prompt: str, **kwargs: Any) -> str:
        """Single-turn text invoke.

        Keyword options: ``system``, ``protocol``, ``max_tokens``, ``temperature``,
        ``response_format`` (``"text"`` | ``"json"``), ``timeout_s``. Remaining
        kwargs are passed to the bound chat model.
        """
        model, messages, extra = self._prepare_text_call(prompt, kwargs)
        response = model.invoke(messages, **extra)
        return stringify_content(getattr(response, "content", response))

    async def ainvoke_text(self, prompt: str, **kwargs: Any) -> str:
        """Async variant of :meth:`invoke_text`."""
        model, messages, extra = self._prepare_text_call(prompt, kwargs)
        response = await model.ainvoke(messages, **extra)
        return stringify_content(getattr(response, "content", response))

    def stream_text(
        self,
        prompt: str,
        *,
        system: str | None = None,
        protocol: str = "langgraph",
        **kwargs: Any,
    ) -> Iterator[str]:
        del protocol
        messages = build_text_messages(prompt, system=system)
        for chunk in self._chat_model.stream(messages, **kwargs):
            text = stringify_content(getattr(chunk, "content", chunk))
            if text:
                yield text

    async def astream_text(
        self,
        prompt: str,
        *,
        system: str | None = None,
        protocol: str = "langgraph",
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        del protocol
        messages = build_text_messages(prompt, system=system)
        async for chunk in self._chat_model.astream(messages, **kwargs):
            text = stringify_content(getattr(chunk, "content", chunk))
            if text:
                yield text


__all__ = ["ModelAccess"]
