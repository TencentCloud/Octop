"""Forced conversation compaction (SummarizationMiddleware offload + summary).

deepagents auto-summarizes when fraction/token thresholds are hit. Slash
``/compact`` needs the same offload + summary path on demand, without waiting
for the auto trigger and without starting a new thread.

Force policy is intentionally **more aggressive** than auto-compaction:
auto keeps ~10% of the window; ``/compact`` keeps a small recent message
tail so users see a clear drop in model context.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from typing import Any, cast

from langchain_core.runnables.config import RunnableConfig, var_child_runnable_config

from octop_harness.backends.utils import DEFENSIVE_OP_ERRORS
from octop_harness.context_usage import (
    conversation_tokens_from_messages,
    estimate_tokens,
    message_content_text,
)
from octop_harness.middleware.memory_recall import replay_recall_snapshots

logger = logging.getLogger(__name__)

# Keep the last N messages after a manual /compact (auto uses ~10% fraction).
FORCE_KEEP_MESSAGES = 6
# Need enough effective history before a forced compact is worthwhile.
MIN_EFFECTIVE_MESSAGES = FORCE_KEEP_MESSAGES + 2
# Avoid "summarized 1 message" no-ops that feel broken.
MIN_SUMMARIZE_MESSAGES = 2


@dataclass(frozen=True)
class CompactResult:
    """Outcome of :meth:`HarnessAgent.acompact_conversation`."""

    ok: bool
    summarized_count: int = 0
    preserved_count: int = 0
    file_path: str | None = None
    reason: str = "ok"  # ok | nothing_to_compact | unavailable | error
    error: str | None = None
    removed_tokens: int = 0
    """Estimated prompt tokens the offloaded messages occupied, minus the summary.

    Compaction makes no model call, so callers holding a context-usage
    snapshot have no fresh provider number to refresh it with; this is the
    delta they can subtract instead. Estimate, not a provider count.
    """
    display_path: str | None = None
    """POSIX workspace-relative path for UI (no host drive / home / backslashes)."""


def display_offload_path(file_path: str | None, session_id: str = "") -> str:
    """Workspace-relative POSIX path for a compact offload file.

    Accepts POSIX or Windows host paths on any OS (including ``\\\\?\\``
    extended paths). ``pathlib.Path`` on Linux treats ``C:\\Users\\...`` as a
    single name, so this slash-normalizes first and never uses host ``Path``.
    """
    raw = str(file_path or "").strip()
    if raw:
        relative = _history_relative_from_host_path(raw)
        if relative:
            return relative
    if session_id:
        return f"conversation_history/{session_id}.md"
    return ""


def _history_relative_from_host_path(raw_path: str) -> str:
    normalized = raw_path.replace("\\", "/")
    if normalized.startswith("//?/"):
        normalized = normalized[4:]
    elif normalized.startswith("//"):
        # UNC //server/share/rest — drop the share prefix; keep looking
        # for conversation_history in the remaining segments.
        parts_unc = [part for part in normalized.split("/") if part]
        if len(parts_unc) >= 2:
            normalized = "/" + "/".join(parts_unc[2:])
    parts = [part for part in normalized.split("/") if part]
    if parts and len(parts[0]) == 2 and parts[0][1] == ":":
        parts = parts[1:]
    if "conversation_history" in parts:
        idx = parts.index("conversation_history")
        start = idx - 1 if idx > 0 and parts[idx - 1].startswith(".") else idx
        return "/".join(parts[start:])
    name = parts[-1] if parts else ""
    if name.endswith(".md"):
        return f"conversation_history/{name}"
    return ""


def _resolve_offload_backend(summarization_middleware: Any | None, backend: Any) -> Any:
    """Prefer the graph middleware's backend (workspace-scoped artifacts_root)."""
    if summarization_middleware is not None:
        mw_backend = getattr(summarization_middleware, "_backend", None)
        if mw_backend is not None and not callable(mw_backend):
            return mw_backend
    return backend


def _build_force_summarization_middleware(model: Any, backend: Any) -> Any:
    """Build a one-shot middleware with aggressive keep + the turn summary model."""
    from deepagents.middleware.summarization import (
        SummarizationMiddleware,
        compute_summarization_defaults,
    )

    from octop_harness.middleware.memory_recall import count_tokens_with_recall

    defaults = compute_summarization_defaults(model)
    return SummarizationMiddleware(
        model=model,
        backend=backend,
        # Auto-trigger unused for force; keep is intentionally tighter than auto.
        trigger=defaults["trigger"],
        keep=("messages", FORCE_KEEP_MESSAGES),
        token_counter=count_tokens_with_recall,
        truncate_args_settings=defaults.get("truncate_args_settings"),
    )


def _is_summarization_middleware(obj: Any) -> bool:
    name = getattr(obj, "serialized_name", None) or getattr(type(obj), "serialized_name", None)
    if name == "SummarizationMiddleware":
        return True
    cls_name = type(obj).__name__
    return "SummarizationMiddleware" in cls_name


def _has_reusable_helper(mw: Any) -> bool:
    """True when *mw* is a real SummarizationMiddleware we can temporarily retune."""
    helper = getattr(mw, "_lc_helper", None)
    keep = getattr(helper, "keep", None)
    return isinstance(keep, tuple) and len(keep) == 2


@contextmanager
def _force_policy(mw: Any, model: Any) -> Iterator[Any]:
    """Apply force keep + turn summary model on the graph MW; restore after."""
    helper = mw._lc_helper
    old_keep = helper.keep
    old_model = helper.model
    old_summary = helper._summary_model
    helper.keep = ("messages", FORCE_KEEP_MESSAGES)
    helper.model = model
    bind_retry = getattr(model, "with_retry", None)
    helper._summary_model = bind_retry() if callable(bind_retry) else model
    try:
        yield mw
    finally:
        helper.keep = old_keep
        helper.model = old_model
        helper._summary_model = old_summary


def _resolve_offload_session_id(mw: Any, values: dict[str, Any]) -> str:
    """Reuse deepagents' history-file id so later auto-compacts append."""
    getter = getattr(mw, "_get_session_id", None)
    if callable(getter):
        sid = getter(values)
        if isinstance(sid, str) and sid:
            return sid
    existing = values.get("_summarization_session_id")
    if isinstance(existing, str) and existing:
        return existing
    return f"session_{uuid.uuid4().hex}"


def _partition_for_force(
    *,
    apply_mw: Any,
    force_mw: Any,
    messages: list[Any],
    event: Any,
) -> CompactResult | tuple[list[Any], list[Any], int]:
    """Return nothing-to-compact, or ``(to_summarize, preserved, cutoff)``."""
    effective = apply_mw._apply_event_to_messages(messages, event)
    if len(effective) < MIN_EFFECTIVE_MESSAGES:
        return CompactResult(ok=False, reason="nothing_to_compact")

    cutoff = force_mw._determine_cutoff_index(effective)
    if cutoff <= 0:
        return CompactResult(ok=False, reason="nothing_to_compact")

    to_summarize, preserved = force_mw._partition_messages(effective, cutoff)
    if len(to_summarize) < MIN_SUMMARIZE_MESSAGES:
        return CompactResult(ok=False, reason="nothing_to_compact")
    return to_summarize, preserved, cutoff


async def _summarize_and_offload(
    *,
    work_mw: Any,
    offload_backend: Any,
    to_summarize: list[Any],
    session_id: str,
    config: dict[str, Any],
    thread_id: str,
) -> CompactResult | tuple[Any, str]:
    """Offload history + create summary. ``file_path is None`` is a hard fail."""
    token = var_child_runnable_config.set(cast(RunnableConfig, config))
    try:
        try:
            # Inline media must finish first (rewrites message content for both paths).
            # History offload and summary LLM are independent — run concurrently
            # (same as deepagents SummarizationMiddleware.abefore_model).
            offloaded = to_summarize
            aoffload_media = getattr(work_mw, "_aoffload_inline_media", None)
            if callable(aoffload_media):
                offloaded, _failed = await aoffload_media(offload_backend, to_summarize)

            file_path, summary = await asyncio.gather(
                work_mw._aoffload_to_backend(offload_backend, offloaded, session_id),
                work_mw._acreate_summary(offloaded),
            )
        except Exception as exc:  # offload/summary failure degrades compaction; pylint: disable=broad-except
            logger.exception("acompact: summarization failed for thread=%s", thread_id)
            return CompactResult(ok=False, reason="error", error=str(exc))
    finally:
        var_child_runnable_config.reset(token)

    if file_path is None:
        logger.error(
            "acompact: history offload failed for thread=%s; conversation not compacted",
            thread_id,
        )
        return CompactResult(ok=False, reason="error", error="history offload failed")
    return file_path, summary


async def _persist_compact_event(
    *,
    graph: Any,
    config: dict[str, Any],
    work_mw: Any,
    event: Any,
    cutoff: int,
    file_path: Any,
    summary: str,
    session_id: str,
    to_summarize: list[Any],
    preserved: list[Any],
    thread_id: str,
) -> CompactResult:
    summary_msg = work_mw._build_new_messages_with_path(summary, file_path)[0]
    removed_tokens = max(
        0,
        conversation_tokens_from_messages(replay_recall_snapshots(to_summarize))
        - estimate_tokens(message_content_text(getattr(summary_msg, "content", ""))),
    )
    new_event = {
        "cutoff_index": work_mw._compute_state_cutoff(event, cutoff),
        "summary_message": summary_msg,
        "file_path": file_path,
    }
    shown = display_offload_path(file_path, session_id) or None
    try:
        await graph.aupdate_state(
            config,
            {
                "_summarization_event": new_event,
                "_summarization_session_id": session_id,
            },
        )
    except DEFENSIVE_OP_ERRORS as exc:
        logger.warning("acompact: aupdate_state failed for %r", thread_id, exc_info=True)
        return CompactResult(
            ok=False,
            reason="error",
            error=str(exc),
            summarized_count=len(to_summarize),
            preserved_count=len(preserved),
            file_path=file_path,
            display_path=shown,
        )
    return CompactResult(
        ok=True,
        reason="ok",
        summarized_count=len(to_summarize),
        preserved_count=len(preserved),
        file_path=file_path,
        display_path=shown,
        removed_tokens=removed_tokens,
    )


async def force_compact_thread(
    *,
    graph: Any,
    backend: Any,
    model: Any,
    thread_id: str,
    model_ref: str | None = None,
    summarization_middleware: Any | None = None,
) -> CompactResult:
    """Summarize+offload older messages for *thread_id*; update ``_summarization_event``.

    Always uses a force-specific keep policy (last
    :data:`FORCE_KEEP_MESSAGES` messages) and *model* for summary generation.
    Prefers the graph middleware (same backend / session id / apply-event)
    and only builds a one-shot instance when that MW is missing.
    """
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    if model_ref:
        config["configurable"]["model"] = model_ref

    try:
        state = await graph.aget_state(config)
    except DEFENSIVE_OP_ERRORS as exc:
        logger.warning("acompact: aget_state failed for %r", thread_id, exc_info=True)
        return CompactResult(ok=False, reason="unavailable", error=str(exc))

    values = getattr(state, "values", None) or {}
    if not isinstance(values, dict):
        values = {}
    messages = list(values.get("messages") or [])
    event = values.get("_summarization_event")

    graph_mw = summarization_middleware if _is_summarization_middleware(summarization_middleware) else None
    offload_backend = _resolve_offload_backend(graph_mw, backend)

    reuse = graph_mw is not None and _has_reusable_helper(graph_mw)
    if reuse:
        mw_cm: Any = _force_policy(graph_mw, model)
    else:
        try:
            force_mw = _build_force_summarization_middleware(model, offload_backend)
        except DEFENSIVE_OP_ERRORS as exc:
            return CompactResult(ok=False, reason="unavailable", error=str(exc))
        mw_cm = nullcontext(force_mw)

    with mw_cm as work_mw:
        apply_mw = graph_mw if graph_mw is not None else work_mw
        prepared = _partition_for_force(apply_mw=apply_mw, force_mw=work_mw, messages=messages, event=event)
        if isinstance(prepared, CompactResult):
            return prepared
        to_summarize, preserved, cutoff = prepared
        session_id = _resolve_offload_session_id(work_mw, values)
        produced = await _summarize_and_offload(
            work_mw=work_mw,
            offload_backend=offload_backend,
            to_summarize=to_summarize,
            session_id=session_id,
            config=config,
            thread_id=thread_id,
        )
        if isinstance(produced, CompactResult):
            return produced
        file_path, summary = produced
        return await _persist_compact_event(
            graph=graph,
            config=config,
            work_mw=work_mw,
            event=event,
            cutoff=cutoff,
            file_path=file_path,
            summary=summary,
            session_id=session_id,
            to_summarize=to_summarize,
            preserved=preserved,
            thread_id=thread_id,
        )


__all__ = [
    "FORCE_KEEP_MESSAGES",
    "MIN_EFFECTIVE_MESSAGES",
    "MIN_SUMMARIZE_MESSAGES",
    "CompactResult",
    "display_offload_path",
    "force_compact_thread",
]
