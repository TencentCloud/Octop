"""Trajectory compatibility view over shared history bodies and untouched legacy rows."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import asdict
from typing import Any, cast

from octop.infra.history.service import HistoryArchive
from octop.infra.trajectory.store import TrajectoryStore
from octop.infra.trajectory.types import TrajectoryEvent, TrajectoryKind


def event_from_dict(value: dict[str, Any]) -> TrajectoryEvent:
    return TrajectoryEvent(
        event_id=value["event_id"],
        agent_id=value["agent_id"],
        thread_id=value["thread_id"],
        seq=value["seq"],
        ts=value["ts"],
        kind=cast(TrajectoryKind, value["kind"]),
        turn_id=value.get("turn_id"),
        request_seq=value.get("request_seq"),
        is_error=value.get("is_error", False),
        summary=value.get("summary", ""),
        payload=value.get("payload", {}),
    )


class ArchiveTrajectoryStore(TrajectoryStore):
    def __init__(self, archive: HistoryArchive) -> None:
        super().__init__(archive.events)
        self.archive = archive

    def record_failure(self, thread_id: str) -> None:
        self.archive.trajectory_errors.add(thread_id)

    def append(self, event: TrajectoryEvent) -> bool:
        return self._write(event, upsert=False)

    def upsert(self, event: TrajectoryEvent) -> bool:
        return self._write(event, upsert=True)

    def _write(self, event: TrajectoryEvent, *, upsert: bool) -> bool:
        turn = self.archive.store.turn(event.thread_id)
        if turn is None or turn["format"] != "v2":
            return super().upsert(event) if upsert else super().append(event)
        with self.archive.store.transaction() as conn:
            self.archive.store.put_document(
                conn,
                doc_id="event:" + event.event_id,
                thread_id=event.thread_id,
                turn_id=turn["id"],
                kind="event",
                seq=event.seq,
                value=asdict(event),
            )
        return True

    def list_before(
        self, thread_id: str, *, before_seq: int | None, limit: int, kinds: list[str] | None
    ) -> list[TrajectoryEvent]:
        if limit <= 0:
            return []
        rows = super().list_before(thread_id, before_seq=before_seq, limit=limit, kinds=kinds)
        new: list[TrajectoryEvent] = []
        boundary = before_seq
        while len(new) < limit:
            batch = self.archive.store.event_page(thread_id, boundary, max(limit, 100))
            if not batch:
                break
            new.extend(event_from_dict(e) for e in batch if kinds is None or e["kind"] in kinds)
            boundary = batch[-1]["seq"]
        return sorted([*rows, *new[:limit]], key=lambda event: event.seq)[-limit:]

    def get(self, event_id: str) -> TrajectoryEvent | None:
        value = self.archive.store.get_event(event_id)
        return event_from_dict(value) if value is not None else super().get(event_id)

    def iter_for_export(self, thread_id: str) -> Iterator[TrajectoryEvent]:
        legacy = list(super().iter_for_export(thread_id))
        new = [
            event_from_dict(d["value"]) for d in self.archive.store.documents(thread_id, "event")
        ]
        yield from sorted([*legacy, *new], key=lambda event: event.seq)

    def delete_for_thread(self, thread_id: str) -> int:
        count = super().delete_for_thread(thread_id)
        self.archive.remove_thread(thread_id)
        return count
