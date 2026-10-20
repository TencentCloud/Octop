"""Runtime slash: context building, request parsing, and stream/call interception."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING, Any

from octop_harness.request import ChatRequest
from octop_harness.slash.core import (
    BufferSink,
    RuntimeSlashCtx,
    RuntimeSlashDispatcher,
    build_runtime_dispatcher,
    parse_slash,
)

if TYPE_CHECKING:
    from octop_harness.agent import HarnessAgent

StreamBody = Callable[[ChatRequest], AsyncIterator[Any]]
CallBody = Callable[[ChatRequest], Awaitable[dict[str, Any]]]


def slash_text_from_request(request: ChatRequest) -> str | None:
    """Extract slash-eligible user text from a single-message :class:`ChatRequest`."""
    messages = request.messages
    if isinstance(messages, str):
        return messages
    if isinstance(messages, list) and len(messages) == 1:
        item = messages[0]
        if isinstance(item, dict) and item.get("role") == "user":
            content = item.get("content")
            if isinstance(content, str):
                return content
    return None


def build_runtime_ctx(
    agent: HarnessAgent,
    request: ChatRequest,
    *,
    locale: str = "zh",
    list_skills: Callable[[], Awaitable[list[dict[str, Any]]]] | None = None,
) -> RuntimeSlashCtx:
    """Build slash context for a :class:`HarnessAgent` invocation."""
    agent_id = request.agent_id or "default"
    thread_id = request.thread_id

    def _cancel(_agent_id: str, tid: str) -> None:
        agent.cancel(tid)

    def _get(_agent_id: str, tid: str) -> str | None:
        return agent.get_thread_model(tid)

    def _set(_agent_id: str, tid: str, model: str) -> None:
        agent.set_thread_model(tid, model)

    def _clear(_agent_id: str, tid: str) -> None:
        agent.clear_thread_model(tid)

    return RuntimeSlashCtx(
        agent_id=agent_id,
        thread_id=thread_id,
        locale=locale,
        default_model=agent.config.pick_default_model_ref(),
        cancel_stream=_cancel,
        get_thread_model=_get,
        set_thread_model=_set,
        clear_thread_model=_clear,
        list_skills=list_skills,
    )


async def try_handle_runtime_slash(
    text: str | None,
    *,
    ctx: RuntimeSlashCtx,
    dispatcher: RuntimeSlashDispatcher | None = None,
) -> tuple[bool, list[str]]:
    """Return ``(handled, lines)``. *handled* is False when *text* is not a runtime slash."""
    cmd = parse_slash(text)
    if cmd is None:
        return False, []
    d = dispatcher or build_runtime_dispatcher()
    if not d.has(cmd.name):
        return False, []
    sink = BufferSink()
    await d.handle(cmd, ctx, sink)
    return True, sink.lines


async def runtime_slash_stream_chunks(
    text: str | None,
    *,
    ctx: RuntimeSlashCtx,
    dispatcher: RuntimeSlashDispatcher | None = None,
) -> list[dict[str, str]] | None:
    """Return langgraph-style chunks when *text* is a handled runtime slash."""
    handled, lines = await try_handle_runtime_slash(text, ctx=ctx, dispatcher=dispatcher)
    if not handled:
        return None
    chunks: list[dict[str, str]] = [{"type": "token", "content": f"{line}\n"} for line in lines]
    chunks.append({"type": "done"})
    return chunks


async def iter_with_runtime_slash(
    request: ChatRequest,
    *,
    ctx: RuntimeSlashCtx,
    stream: StreamBody,
    dispatcher: RuntimeSlashDispatcher | None = None,
) -> AsyncIterator[Any]:
    """Yield slash chunks or delegate to *stream* — single interception entry."""
    slash_text = slash_text_from_request(request)
    if slash_text is not None:
        chunks = await runtime_slash_stream_chunks(slash_text, ctx=ctx, dispatcher=dispatcher)
        if chunks is not None:
            for chunk in chunks:
                yield chunk
            return
    async for chunk in stream(request):
        yield chunk


async def call_with_runtime_slash(
    request: ChatRequest,
    *,
    ctx: RuntimeSlashCtx,
    call: CallBody,
    dispatcher: RuntimeSlashDispatcher | None = None,
) -> dict[str, Any]:
    """Return slash result or delegate to *call* — single interception entry."""
    slash_text = slash_text_from_request(request)
    if slash_text is not None:
        chunks = await runtime_slash_stream_chunks(slash_text, ctx=ctx, dispatcher=dispatcher)
        if chunks is not None:
            text = "".join(c.get("content", "") for c in chunks if c.get("type") == "token")
            return {"type": "slash", "content": text.strip()}
    return await call(request)
