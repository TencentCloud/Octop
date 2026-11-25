"""The turn history tracker claims its single write per turn."""

from __future__ import annotations

from octop.infra.history.projection import TurnHistoryTracker


def test_mark_persisted_is_single_use() -> None:
    tracker = TurnHistoryTracker.from_request({})

    assert tracker.persisted is False
    assert tracker.mark_persisted() is True
    assert tracker.persisted is True
    assert tracker.mark_persisted() is False


def test_persisted_flag_is_per_tracker() -> None:
    first = TurnHistoryTracker.from_request({})
    second = TurnHistoryTracker.from_request({})

    assert first.mark_persisted() is True
    assert second.mark_persisted() is True
