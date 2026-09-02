"""TrajectoryLiveBus — in-process pub/sub per thread_id."""

from __future__ import annotations

from octop.infra.trajectory.live import TrajectoryLiveBus


def test_publish_delivers_to_subscriber() -> None:
    bus = TrajectoryLiveBus()
    queue = bus.subscribe("T1")
    message = {"event_id": "e1", "kind": "user"}

    bus.publish("T1", message)

    assert queue.get_nowait() == message


def test_unsubscribe_stops_delivery_and_isolates_threads() -> None:
    bus = TrajectoryLiveBus()
    t1 = bus.subscribe("T1")
    t2 = bus.subscribe("T2")

    bus.unsubscribe("T1", t1)
    bus.publish("T1", {"event_id": "dropped"})
    bus.publish("T2", {"event_id": "kept"})

    assert t1.empty()
    assert t2.get_nowait() == {"event_id": "kept"}
