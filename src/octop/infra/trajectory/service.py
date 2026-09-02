"""Orchestrate project → store → live publish. Observe never fails the caller."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from octop.infra.trajectory.live import TrajectoryLiveBus
from octop.infra.trajectory.metrics import TrajectoryMetrics, aggregate_metrics
from octop.infra.trajectory.projector import project_harness_chunk
from octop.infra.trajectory.store import TrajectoryStore
from octop.infra.trajectory.types import TrajectoryEvent

logger = logging.getLogger(__name__)


@dataclass
class _ThreadInFlight:
    assistant: TrajectoryEvent | None = None
    tools: dict[str, TrajectoryEvent] = field(default_factory=dict)


class TrajectoryService:
    def __init__(self, store: TrajectoryStore, bus: TrajectoryLiveBus) -> None:
        self._store = store
        self._bus = bus
        self._inflight: dict[str, _ThreadInFlight] = {}

    def observe_chunk(self, agent_id: str, thread_id: str, chunk: dict[str, Any]) -> None:
        try:
            events = project_harness_chunk(chunk, agent_id=agent_id, thread_id=thread_id, seq=0)
            for event in events:
                if event.kind == "assistant":
                    self._observe_assistant(event)
                elif event.kind == "tool":
                    self._observe_tool(event)
                else:
                    self._clear_assistant(event.thread_id)
                    self._commit_new(event)
        except Exception:
            logger.exception(
                "trajectory observe_chunk failed agent=%s thread=%s",
                agent_id,
                thread_id,
            )

    def replace_store(self, store: TrajectoryStore) -> None:
        """Point append/list at a rebound control-plane pool."""
        self._store = store

    def list_events(
        self,
        thread_id: str,
        *,
        before_seq: int | None,
        limit: int,
        kinds: list[str] | None,
    ) -> list[TrajectoryEvent]:
        return self._store.list_before(thread_id, before_seq=before_seq, limit=limit, kinds=kinds)

    def get_event(self, event_id: str) -> TrajectoryEvent | None:
        return self._store.get(event_id)

    def metrics(self, thread_id: str) -> TrajectoryMetrics:
        return aggregate_metrics(list(self._store.iter_for_export(thread_id)))

    def export_jsonl(self, thread_id: str) -> Iterator[str]:
        for event in self._store.iter_for_export(thread_id):
            yield json.dumps(asdict(event), ensure_ascii=False)

    def delete_for_thread(self, thread_id: str) -> int:
        self._inflight.pop(thread_id, None)
        return self._store.delete_for_thread(thread_id)

    def _observe_assistant(self, event: TrajectoryEvent) -> None:
        state = self._inflight.setdefault(event.thread_id, _ThreadInFlight())
        current = state.assistant
        if current is not None and _same_assistant_request(current, event):
            merged = _merge_assistant(current, event)
            self._upsert(merged)
            state.assistant = merged
            return
        state.assistant = self._commit_new(event)

    def _observe_tool(self, event: TrajectoryEvent) -> None:
        state = self._inflight.setdefault(event.thread_id, _ThreadInFlight())
        state.assistant = None
        call_id = str(event.payload.get("call_id") or "")
        current = state.tools.get(call_id)
        if current is not None:
            merged = _merge_tool(current, event)
            self._upsert(merged)
            state.tools[call_id] = merged
            return
        committed = self._commit_new(event)
        if call_id:
            state.tools[call_id] = committed

    def _clear_assistant(self, thread_id: str) -> None:
        state = self._inflight.get(thread_id)
        if state is not None:
            state.assistant = None

    def _commit_new(self, event: TrajectoryEvent) -> TrajectoryEvent:
        seq = self._next_seq(event.thread_id)
        stored = replace(event, seq=seq, event_id=_stable_event_id(event, seq))
        if self._store.append(stored):
            self._bus.publish(stored.thread_id, asdict(stored))
        return stored

    def _upsert(self, event: TrajectoryEvent) -> None:
        if self._store.upsert(event):
            self._bus.publish(event.thread_id, asdict(event))

    def _next_seq(self, thread_id: str) -> int:
        latest = self._store.list_before(thread_id, before_seq=None, limit=1, kinds=None)
        if not latest:
            return 1
        return latest[0].seq + 1


def _stable_event_id(event: TrajectoryEvent, seq: int) -> str:
    if event.kind == "tool":
        call_id = event.payload.get("call_id")
        return f"{event.thread_id}:{seq}:tool:{call_id}"
    return f"{event.thread_id}:{seq}:{event.kind}"


def _same_assistant_request(current: TrajectoryEvent, incoming: TrajectoryEvent) -> bool:
    if current.request_seq is None or incoming.request_seq is None:
        return True
    return current.request_seq == incoming.request_seq


def _merge_assistant(current: TrajectoryEvent, incoming: TrajectoryEvent) -> TrajectoryEvent:
    content = str(current.payload.get("content") or "") + str(incoming.payload.get("content") or "")
    payload = {**current.payload, **incoming.payload, "content": content}
    return replace(
        current,
        ts=incoming.ts or current.ts,
        summary=content,
        payload=payload,
        request_seq=(
            incoming.request_seq if incoming.request_seq is not None else current.request_seq
        ),
        turn_id=incoming.turn_id or current.turn_id,
    )


def _merge_tool(current: TrajectoryEvent, incoming: TrajectoryEvent) -> TrajectoryEvent:
    payload = dict(current.payload)
    incoming_payload = incoming.payload
    payload["name"] = _merge_name(
        str(payload.get("name") or ""),
        str(incoming_payload.get("name") or ""),
    )
    if "args" in incoming_payload:
        payload["args"] = _merge_args(payload.get("args"), incoming_payload.get("args"))
    if "result" in incoming_payload:
        payload["result"] = incoming_payload["result"]
    name = str(payload.get("name") or "tool")
    return replace(
        current,
        ts=incoming.ts or current.ts,
        summary=f"tool {name}",
        payload=payload,
        is_error=current.is_error or incoming.is_error,
        request_seq=(
            incoming.request_seq if incoming.request_seq is not None else current.request_seq
        ),
        turn_id=incoming.turn_id or current.turn_id,
    )


def _merge_name(left: str, right: str) -> str:
    if not left or left == "tool":
        return right or left or "tool"
    if not right or right == "tool":
        return left
    if right.startswith(left):
        return right
    if left.startswith(right):
        return left
    return left + right


def _merge_args(left: Any, right: Any) -> Any:
    if right is None:
        return left
    if left is None or left == "":
        return right
    if isinstance(left, str) and isinstance(right, str):
        return left + right
    if isinstance(left, dict) and isinstance(right, dict):
        return {**left, **right}
    return right
