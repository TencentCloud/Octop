"""Append-only trajectory ledger — thin wrapper around TrajectoryEventRepo."""

from __future__ import annotations

from collections.abc import Iterator

from octop.infra.db.repos.trajectory_events import TrajectoryEventRepo
from octop.infra.trajectory.types import TrajectoryEvent


class TrajectoryStore:
    def __init__(self, repo: TrajectoryEventRepo) -> None:
        self._repo = repo

    def append(self, event: TrajectoryEvent) -> bool:
        return self._repo.append(event)

    def upsert(self, event: TrajectoryEvent) -> bool:
        return self._repo.upsert(event)

    def list_before(
        self,
        thread_id: str,
        *,
        before_seq: int | None,
        limit: int,
        kinds: list[str] | None,
    ) -> list[TrajectoryEvent]:
        return self._repo.list_before(thread_id, before_seq=before_seq, limit=limit, kinds=kinds)

    def get(self, event_id: str) -> TrajectoryEvent | None:
        return self._repo.get(event_id)

    def delete_for_thread(self, thread_id: str) -> int:
        return self._repo.delete_for_thread(thread_id)

    def iter_for_export(self, thread_id: str) -> Iterator[TrajectoryEvent]:
        return self._repo.iter_for_export(thread_id)
