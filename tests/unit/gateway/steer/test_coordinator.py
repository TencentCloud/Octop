"""Unit tests for SteerCoordinator admission / drain / discard."""

from __future__ import annotations

from octop.infra.gateway.steer.coordinator import DiscardBundle, DrainBundle, SteerCoordinator
from octop.infra.gateway.steer.types import SteerAdmitOk, SteerAdmitReject


def test_idle_auto_returns_none() -> None:
    c = SteerCoordinator()
    assert c.admit("t1", text="hi", client_pending_id="a", expected_turn_id=None) is None


def test_queue_drain_continuation() -> None:
    c = SteerCoordinator()
    turn_id, _seq = c.begin_turn("t1")
    r1 = c.admit(
        "t1",
        text="one",
        client_pending_id="c1",
        expected_turn_id=turn_id,
    )
    assert isinstance(r1, SteerAdmitOk) and r1.emit_queued
    r2 = c.admit(
        "t1",
        text="two",
        client_pending_id="c2",
        expected_turn_id=turn_id,
    )
    assert isinstance(r2, SteerAdmitOk) and r2.queue_length == 2

    drained = c.drain_for_continuation("t1")
    assert isinstance(drained, DrainBundle)
    assert drained.text == "one\n---\ntwo"
    assert drained.client_pending_ids == ["c1", "c2"]
    assert c.get_state("t1") is not None
    assert c.get_state("t1").queue == []  # type: ignore[union-attr]


def test_hitl_paused_rejects() -> None:
    c = SteerCoordinator()
    turn_id, _ = c.begin_turn("t1")
    c.set_phase("t1", "hitl_paused")
    r = c.admit(
        "t1",
        text="x",
        client_pending_id="c1",
        expected_turn_id=turn_id,
    )
    assert isinstance(r, SteerAdmitReject)
    assert r.reason == "hitl_paused"
    assert r.seq is not None


def test_expected_turn_mismatch() -> None:
    c = SteerCoordinator()
    c.begin_turn("t1")
    r = c.admit(
        "t1",
        text="x",
        client_pending_id="c1",
        expected_turn_id="wrong",
    )
    assert isinstance(r, SteerAdmitReject)
    assert r.reason == "expected_turn_id_mismatch"


def test_idempotent_retry() -> None:
    c = SteerCoordinator()
    turn_id, _ = c.begin_turn("t1")
    first = c.admit(
        "t1",
        text="hello",
        client_pending_id="c1",
        expected_turn_id=turn_id,
    )
    assert isinstance(first, SteerAdmitOk)
    second = c.admit(
        "t1",
        text="different",
        client_pending_id="c1",
        expected_turn_id=turn_id,
    )
    assert isinstance(second, SteerAdmitOk)
    assert second.status == "idempotent"
    assert second.pending_id == first.pending_id
    assert c.get_state("t1").queue[0].text == "hello"  # type: ignore[union-attr]


def test_discard_on_cancel() -> None:
    c = SteerCoordinator()
    turn_id, _ = c.begin_turn("t1")
    c.admit(
        "t1",
        text="bye",
        client_pending_id="c1",
        expected_turn_id=turn_id,
    )
    c.mark_cancelling("t1")
    bundle = c.discard("t1", reason="turn_cancelled")
    assert isinstance(bundle, DiscardBundle)
    assert bundle.reason == "turn_cancelled"
    assert bundle.client_pending_ids == ["c1"]


def test_follow_up_while_busy() -> None:
    c = SteerCoordinator()
    c.begin_turn("t1")
    r = c.admit(
        "t1",
        text="",
        client_pending_id=None,
        expected_turn_id=None,
        delivery="follow_up",
    )
    assert isinstance(r, SteerAdmitReject)
    assert r.reason == "turn_active"


def test_auto_busy_mints_client_pending_id_and_binds_turn() -> None:
    """Busy ``delivery=auto`` without ids still steers (flush race safety)."""
    c = SteerCoordinator()
    turn_id, _ = c.begin_turn("t1")
    r = c.admit(
        "t1",
        text="steer me",
        client_pending_id=None,
        expected_turn_id=None,
        delivery="auto",
    )
    assert isinstance(r, SteerAdmitOk)
    assert r.status == "queued"
    assert r.turn_id == turn_id
    assert r.client_pending_id
    assert r.emit_queued is True


def test_queue_full() -> None:
    c = SteerCoordinator()
    turn_id, _ = c.begin_turn("t1")
    for i in range(8):
        r = c.admit(
            "t1",
            text=f"m{i}",
            client_pending_id=f"c{i}",
            expected_turn_id=turn_id,
        )
        assert isinstance(r, SteerAdmitOk)
    r = c.admit(
        "t1",
        text="overflow",
        client_pending_id="cx",
        expected_turn_id=turn_id,
    )
    assert isinstance(r, SteerAdmitReject)
    assert r.reason == "queue_full"


def test_snapshot_while_live() -> None:
    c = SteerCoordinator()
    turn_id, seq = c.begin_turn("t1")
    c.admit(
        "t1",
        text="snap",
        client_pending_id="c1",
        expected_turn_id=turn_id,
    )
    frames = c.snapshot_frames("t1")
    assert frames[0]["type"] == "steer.queue_snapshot"
    assert frames[0]["turn_id"] == turn_id
    assert frames[0]["queue_length"] == 1
    assert frames[1]["type"] == "turn.resumed"
    assert frames[1]["turn_id"] == turn_id
    assert frames[1]["seq"] == frames[0]["seq"]
    assert frames[0]["seq"] >= seq


def test_remove_queued() -> None:
    c = SteerCoordinator()
    turn_id, _ = c.begin_turn("t1")
    admitted = c.admit(
        "t1",
        text="rm",
        client_pending_id="c1",
        expected_turn_id=turn_id,
    )
    assert isinstance(admitted, SteerAdmitOk)
    result = c.remove(
        "t1",
        turn_id=turn_id,
        client_pending_id="c1",
        pending_id=admitted.pending_id,
    )
    assert result.status == "removed"
    assert result.emit_removed
    assert c.get_state("t1").queue == []  # type: ignore[union-attr]


def test_has_pending_and_is_hitl_paused() -> None:
    c = SteerCoordinator()
    turn_id, _ = c.begin_turn("t1")
    assert c.has_pending("t1") is False
    assert c.is_hitl_paused("t1") is False
    assert isinstance(
        c.admit("t1", text="x", client_pending_id="c1", expected_turn_id=turn_id),
        SteerAdmitOk,
    )
    assert c.has_pending("t1") is True
    c.set_phase("t1", "hitl_paused")
    assert c.is_hitl_paused("t1") is True


def test_end_turn_hitl_parks_queue_until_taken() -> None:
    c = SteerCoordinator()
    turn_id, _ = c.begin_turn("t1")
    assert isinstance(
        c.admit("t1", text="x", client_pending_id="c1", expected_turn_id=turn_id),
        SteerAdmitOk,
    )
    c.set_phase("t1", "hitl_paused")
    assert c.end_turn("t1") is None  # parked, not discarded
    assert c.has_pending("t1") is True
    # Admission during the pause still rejects.
    rejected = c.admit("t1", text="y", client_pending_id="c2", expected_turn_id=turn_id)
    assert rejected.status == "rejected"
    taken = c.take_hitl_pending("t1")
    assert taken is not None
    bundle, seq = taken
    assert bundle.text == "x"
    assert seq > 0
    assert c.has_pending("t1") is False
    assert c.take_hitl_pending("t1") is None
