"""Orchestrate project → store → live publish. Observe never fails the caller."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import asdict
from typing import Any

from octop.infra.trajectory.live import TrajectoryLiveBus
from octop.infra.trajectory.metrics import TrajectoryMetrics, aggregate_metrics
from octop.infra.trajectory.projector import project_harness_chunk
from octop.infra.trajectory.store import TrajectoryStore
from octop.infra.trajectory.types import TrajectoryEvent

logger = logging.getLogger(__name__)


class TrajectoryService:
    def __init__(self, store: TrajectoryStore, bus: TrajectoryLiveBus) -> None:
        self._store = store
        self._bus = bus

    def observe_chunk(self, agent_id: str, thread_id: str, chunk: dict[str, Any]) -> None:
        try:
            seq = self._next_seq(thread_id)
            events = project_harness_chunk(chunk, agent_id=agent_id, thread_id=thread_id, seq=seq)
            for event in events:
                if self._store.append(event):
                    self._bus.publish(thread_id, asdict(event))
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
        return self._store.delete_for_thread(thread_id)

    def _next_seq(self, thread_id: str) -> int:
        latest = self._store.list_before(thread_id, before_seq=None, limit=1, kinds=None)
        if not latest:
            return 1
        return latest[0].seq + 1
