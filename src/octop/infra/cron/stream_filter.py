"""Raw-chunk stream filter for cron agent delivery (#2384).

Cron ``task_type=agent`` runs collapse a whole agent turn into a single pushed
IM message. Text the model emits before calling a regular tool is progress
narration ("I'll start by gathering the current time…") and must not reach the
user. Channel streams already filter this — ``collapse_to_invoke_response``
for invoke mode and ``withhold_weixin_stream_preamble`` for WeChat stream
mode — but the cron path consumed raw harness chunks directly, bypassing both.

This module provides the equivalent filter at the raw-chunk level:

* ``token`` / ``delta`` chunks are withheld until the next boundary decides
  their fate. Text leading into a regular tool call is dropped; text leading
  into ``ask_agent`` is kept (team hosts announce their dispatch line); text
  after the last tool result — the final answer — passes through.
* Tool names may arrive in shards across ``tool_call_chunk`` events, so the
  decision uses the same accumulate-by-index logic the dashboard stream
  projection uses (``stream_project._ToolProjectionState``).
* ``hitl_required`` clears withheld text: the turn aborts and the pending
  narration must not leak into a later delivery.
* All non-text chunks pass through untouched and in order, so history/usage
  trackers and tool-error logging keep working on the filtered stream.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

_TEXT_CHUNK_TYPES = frozenset({"token", "delta"})
_KEEP_NARRATION_TOOLS = frozenset({"ask_agent"})


def _idx_key(chunk: dict[str, Any]) -> str:
    return f"_idx_{chunk.get('index', 0)}"


async def withhold_pretool_stream_chunks(
    chunks: AsyncIterator[dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    """Drop streamed text that only leads into a regular tool call.

    Yields the same chunks (minus dropped narration), preserving order between
    text and the tool boundary that releases it.
    """
    held: list[dict[str, Any]] = []
    tool_names: dict[str, str] = {}
    started: set[str] = set()
    active_idx: str | None = None
    drained = False

    try:
        async for chunk in chunks:
            ctype: str = chunk.get("type", "")

            if ctype in _TEXT_CHUNK_TYPES:
                held.append(chunk)
                continue

            if ctype == "tool_call_chunk":
                idx = _idx_key(chunk)
                active_idx = idx
                name_frag: str = chunk.get("name") or ""
                if name_frag:
                    tool_names[idx] = tool_names.get(idx, "") + name_frag
                args_frag: str = chunk.get("args") or ""
                if args_frag and idx not in started and tool_names.get(idx):
                    started.add(idx)
                    if tool_names[idx] in _KEEP_NARRATION_TOOLS:
                        for item in held:
                            yield item
                    held.clear()
                yield chunk
                continue

            if ctype == "tool_result":
                name = tool_names.get(active_idx or "", "") or ""
                if active_idx is not None:
                    # A result can arrive without streamed call chunks (replayed
                    # history); treat the active tool as started then and there.
                    if active_idx not in started:
                        started.add(active_idx)
                        if name in _KEEP_NARRATION_TOOLS:
                            for item in held:
                                yield item
                    tool_names.pop(active_idx, None)
                    started.discard(active_idx)
                    active_idx = None
                if name not in _KEEP_NARRATION_TOOLS:
                    held.clear()
                yield chunk
                continue

            if ctype == "hitl_required":
                held.clear()
                yield chunk
                continue

            yield chunk

        drained = True
        for item in held:
            yield item
    finally:
        # The consumer drains this generator fully, so an in-flight finally
        # yield only runs when the source stream itself died mid-turn: release
        # the partial text so history projection keeps it (#516) even though
        # the delivery aborts and nothing is pushed to IM.
        if not drained and held:
            for item in held:
                yield item
