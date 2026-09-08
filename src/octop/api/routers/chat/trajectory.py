"""Thread trajectory REST APIs (history, detail, metrics, export, live SSE)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from octop.api.common.content_disposition import content_disposition
from octop.api.deps import current_user, get_server
from octop.api.routers.chat.history import _require_thread
from octop.api.routers.chat.sse import format_sse
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.trajectory.live import TrajectoryLiveBus
from octop.infra.trajectory.service import TrajectoryService
from octop.infra.trajectory.settings import TRAJECTORY_SSE_REPLAY_MAX
from octop.infra.trajectory.types import TrajectoryEvent

router = APIRouter()
logger = logging.getLogger(__name__)

TRAJECTORY_DEFAULT_LIMIT = 100
TRAJECTORY_MAX_LIMIT = 200
TRAJECTORY_SSE_HEARTBEAT_S = 15.0
TRAJECTORY_METRICS_PUSH_INTERVAL_S = 1.0
_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
_LIST_OMIT_PAYLOAD_KEYS = frozenset({"content", "text", "thinking"})
# Keep tool ``args`` / ``result`` on the list endpoint so the ledger can render
# ``name{args} → result`` without a detail fetch. Clip oversized values so a
# single huge tool output cannot bloat the history page.
_LIST_MAX_TOOL_FIELD_CHARS = 2_000
_LIST_MAX_SUMMARY_CHARS = 240
_LIST_CLIP_PAYLOAD_KEYS = frozenset({"args", "result"})


class TrajectoryEventOut(BaseModel):
    event_id: str
    thread_id: str
    agent_id: str
    seq: int
    ts: float
    kind: str
    turn_id: str | None = None
    request_seq: int | None = None
    is_error: bool
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)


class TrajectoryHistoryOut(BaseModel):
    thread_id: str
    events: list[TrajectoryEventOut]
    next_before_seq: int | None = None
    has_more: bool = False


class TrajectoryMetricsOut(BaseModel):
    turns: int
    steps: int
    llm_duration_ms: float | None = None
    tool_duration_ms: float | None = None
    ttft_avg_ms: float | None = None
    tok_per_s: float | None = None
    cache_hit_ratio: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None


def _clamp_limit(limit: int) -> int:
    return max(1, min(limit, TRAJECTORY_MAX_LIMIT))


def _parse_kinds(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    if not raw.strip():
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _trajectory_service(server: Any) -> TrajectoryService:
    runtime = getattr(server, "app_runtime", None)
    service = getattr(runtime, "trajectory_service", None) if runtime is not None else None
    if not isinstance(service, TrajectoryService):
        raise OctopError(ErrorCode.INTERNAL_ERROR, "trajectory service unavailable")
    return service


def _clip_list_payload_value(value: Any) -> Any:
    if isinstance(value, str):
        if len(value) <= _LIST_MAX_TOOL_FIELD_CHARS:
            return value
        return value[:_LIST_MAX_TOOL_FIELD_CHARS] + "…"
    if isinstance(value, (dict, list)):
        raw = json.dumps(value, ensure_ascii=False, default=str)
        if len(raw) <= _LIST_MAX_TOOL_FIELD_CHARS:
            return value
        return raw[:_LIST_MAX_TOOL_FIELD_CHARS] + "…"
    return value


def _summarize_event(event: TrajectoryEvent) -> dict[str, Any]:
    """List-view projection: drop message bodies; keep clipped tool args/result."""
    data = asdict(event)
    summary = str(data.get("summary") or "")
    if len(summary) > _LIST_MAX_SUMMARY_CHARS:
        data["summary"] = summary[: _LIST_MAX_SUMMARY_CHARS - 1].rstrip() + "…"
    payload = data.get("payload")
    if not isinstance(payload, dict):
        data["payload"] = {}
        return data
    summarized: dict[str, Any] = {}
    for key, value in payload.items():
        if key in _LIST_OMIT_PAYLOAD_KEYS:
            continue
        if key in _LIST_CLIP_PAYLOAD_KEYS:
            summarized[key] = _clip_list_payload_value(value)
        else:
            summarized[key] = value
    data["payload"] = summarized
    return data


def _jsonl_lines(service: TrajectoryService, thread_id: str) -> Iterator[str]:
    for line in service.export_jsonl(thread_id):
        yield line + "\n"


def _live_bus(service: TrajectoryService) -> TrajectoryLiveBus:
    return service._bus  # noqa: SLF001


def _resume_after_seq(after_seq: int | None, last_event_id: str | None) -> int | None:
    header_seq: int | None = None
    raw = last_event_id.strip() if last_event_id is not None else ""
    with contextlib.suppress(ValueError):
        header_seq = int(raw) if raw else None
    if after_seq is None:
        return header_seq
    if header_seq is None:
        return after_seq
    return max(after_seq, header_seq)


def _sse_named(event: str, data: Any, *, sse_id: int | None = None) -> str:
    frame = format_sse(event, data)
    if sse_id is None:
        return frame
    return f"id: {sse_id}\n{frame}"


async def _metrics_frame(
    service: TrajectoryService,
    thread_id: str,
    *,
    refresh: bool,
) -> str:
    metrics = await asyncio.to_thread(service.metrics, thread_id, refresh=refresh)
    return format_sse("metrics", asdict(metrics))


def _client_event_payload(message: dict[str, Any]) -> dict[str, Any]:
    outgoing = dict(message)
    outgoing.pop("_final", None)
    return outgoing


async def _iter_trajectory_sse(
    *,
    request: Request,
    service: TrajectoryService,
    thread_id: str,
    after_seq: int | None,
) -> AsyncIterator[str]:
    bus = _live_bus(service)
    queue = bus.subscribe(thread_id)
    last_seq = _resume_after_seq(after_seq, request.headers.get("last-event-id"))
    try:
        if last_seq is not None:
            replay = await asyncio.to_thread(
                service.list_from_seq,
                thread_id,
                from_seq=last_seq,
                limit=TRAJECTORY_SSE_REPLAY_MAX,
            )
            for event in replay:
                payload = asdict(event)
                event_seq = event.seq
                # Re-emit ``seq == after_seq`` so a same-seq tool upsert that
                # landed between REST history and this subscribe still reaches
                # the browser (clients upsert by event_id). Newer seqs follow.
                yield _sse_named("event", payload, sse_id=event_seq)
                if event_seq > last_seq:
                    last_seq = event_seq
        yield await _metrics_frame(service, thread_id, refresh=True)
        last_metrics_at = time.monotonic()
        while True:
            if await request.is_disconnected():
                break
            try:
                message = await asyncio.wait_for(queue.get(), timeout=TRAJECTORY_SSE_HEARTBEAT_S)
            except TimeoutError:
                yield format_sse("heartbeat", {})
                continue
            seq = message.get("seq") if isinstance(message, dict) else None
            # Same-seq upserts (tool args→result) must reach the browser; only
            # drop strictly older frames that can appear after a replay race.
            if isinstance(seq, int) and last_seq is not None and seq < last_seq:
                continue
            outgoing = _client_event_payload(message) if isinstance(message, dict) else message
            yield _sse_named("event", outgoing, sse_id=seq if isinstance(seq, int) else None)
            if isinstance(seq, int):
                last_seq = seq
            force_metrics = isinstance(message, dict) and message.get("_final") is True
            now = time.monotonic()
            if force_metrics or now - last_metrics_at >= TRAJECTORY_METRICS_PUSH_INTERVAL_S:
                yield await _metrics_frame(service, thread_id, refresh=force_metrics)
                last_metrics_at = now
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("trajectory SSE failed thread=%s", thread_id)
        yield format_sse("error", {"message": "trajectory stream failed"})
    finally:
        bus.unsubscribe(thread_id, queue)


@router.get(
    "/agents/{agent_id}/threads/{thread_id}/trajectory",
    summary="Thread trajectory history",
    response_model=TrajectoryHistoryOut,
)
async def get_thread_trajectory(
    agent_id: str,
    thread_id: str,
    limit: int = TRAJECTORY_DEFAULT_LIMIT,
    before_seq: int | None = Query(
        default=None, description="Load events with seq less than this."
    ),
    kinds: str | None = Query(default=None, description="Comma-separated event kinds to include."),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> TrajectoryHistoryOut:
    """Return a page of trajectory events for a thread (newest page by default).

    List payloads omit message bodies (``content`` / ``text`` / ``thinking``) but
    include clipped tool ``args`` / ``result`` for ledger rendering. Use the
    event detail endpoint for full payloads.
    """
    _require_thread(server, agent_id, thread_id, user, as_user)
    page_limit = _clamp_limit(limit)
    parsed_kinds = _parse_kinds(kinds)
    service = _trajectory_service(server)

    def _list() -> list[TrajectoryEvent]:
        return service.list_events(
            thread_id,
            before_seq=before_seq,
            limit=page_limit + 1,
            kinds=parsed_kinds,
        )

    events = await asyncio.to_thread(_list)
    has_more = len(events) > page_limit
    page = events[1:] if has_more else events
    return TrajectoryHistoryOut(
        thread_id=thread_id,
        events=[TrajectoryEventOut.model_validate(_summarize_event(event)) for event in page],
        next_before_seq=page[0].seq if has_more and page else None,
        has_more=has_more,
    )


@router.get(
    "/agents/{agent_id}/threads/{thread_id}/trajectory/events/{event_id}",
    summary="Trajectory event detail",
    response_model=TrajectoryEventOut,
)
async def get_trajectory_event(
    agent_id: str,
    thread_id: str,
    event_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> TrajectoryEventOut:
    """Return one trajectory event with its full payload."""
    _require_thread(server, agent_id, thread_id, user, as_user)
    event = _trajectory_service(server).get_event(event_id)
    if event is None or event.thread_id != thread_id or event.agent_id != agent_id:
        raise OctopError(ErrorCode.NOT_FOUND, f"event {event_id!r} not found")
    return TrajectoryEventOut.model_validate(asdict(event))


@router.get(
    "/agents/{agent_id}/threads/{thread_id}/trajectory/metrics",
    summary="Thread trajectory metrics",
    response_model=TrajectoryMetricsOut,
)
async def get_trajectory_metrics(
    agent_id: str,
    thread_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> TrajectoryMetricsOut:
    """Return aggregated session metrics for a thread's trajectory ledger."""
    _require_thread(server, agent_id, thread_id, user, as_user)
    service = _trajectory_service(server)
    metrics = await asyncio.to_thread(service.metrics, thread_id)
    return TrajectoryMetricsOut.model_validate(asdict(metrics))


@router.get(
    "/agents/{agent_id}/threads/{thread_id}/trajectory/stream",
    summary="Live trajectory SSE stream",
    response_model=None,
)
async def stream_thread_trajectory(
    agent_id: str,
    thread_id: str,
    request: Request,
    after_seq: int | None = Query(
        default=None, description="Replay events with seq greater than this, then follow live."
    ),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> StreamingResponse:
    """Subscribe to live trajectory events for a thread.

    Emits SSE ``event``, ``metrics``, and ``heartbeat`` frames. Resume with
    ``after_seq`` or the ``Last-Event-ID`` header (seq). Disconnect unsubscribes.
    """
    _require_thread(server, agent_id, thread_id, user, as_user)
    service = _trajectory_service(server)

    async def gen() -> AsyncIterator[str]:
        async for frame in _iter_trajectory_sse(
            request=request,
            service=service,
            thread_id=thread_id,
            after_seq=after_seq,
        ):
            yield frame

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get(
    "/agents/{agent_id}/threads/{thread_id}/trajectory/export",
    summary="Export thread trajectory",
    response_model=None,
)
async def export_thread_trajectory(
    agent_id: str,
    thread_id: str,
    format: Literal["jsonl", "json"] = Query(  # noqa: A002
        default="jsonl",
        description="Download format. Default is JSON Lines with full payloads.",
    ),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> StreamingResponse | JSONResponse:
    """Download the full trajectory ledger. Default ``jsonl``; ``json`` returns an array."""
    _require_thread(server, agent_id, thread_id, user, as_user)
    service = _trajectory_service(server)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    if format == "json":
        filename = f"trajectory-{thread_id}-{stamp}.json"
        payload = await asyncio.to_thread(
            lambda: [json.loads(line) for line in service.export_jsonl(thread_id)]
        )
        return JSONResponse(
            payload,
            headers={"Content-Disposition": content_disposition(filename)},
        )
    filename = f"trajectory-{thread_id}-{stamp}.jsonl"
    return StreamingResponse(
        _jsonl_lines(service, thread_id),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": content_disposition(filename)},
    )
