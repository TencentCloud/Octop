"""TurnMeter: in-flight count, time to first token and duration."""

from __future__ import annotations

from tests.support.otel import active_telemetry, metric_points

from octop.infra.gateway.process.usage_record import TurnMeter, UsageTracker


def _active(reader: object) -> int:
    return sum(p.value for p in metric_points(reader, "octop.turn.active"))  # type: ignore[arg-type]


def test_turn_is_in_flight_between_start_and_finish() -> None:
    with active_telemetry() as reader:
        meter = TurnMeter("a1")
        assert metric_points(reader, "octop.turn.active") == []
        meter.start()
        assert _active(reader) == 1
        meter.finish()
        assert _active(reader) == 0
        (point,) = metric_points(reader, "gen_ai.invoke_agent.duration")
    assert point.count == 1


def test_finish_is_idempotent_and_safety_net_does_not_double_count() -> None:
    with active_telemetry() as reader:
        meter = TurnMeter("a1")
        meter.start()
        meter.start()
        meter.finish()
        meter.finish(record_duration=False)
        meter.finish(TimeoutError("late"))
        assert _active(reader) == 0
        (point,) = metric_points(reader, "gen_ai.invoke_agent.duration")
    assert point.count == 1
    assert point.attributes.get("error.type") is None


def test_paused_or_abandoned_turn_leaves_flight_without_duration() -> None:
    with active_telemetry() as reader:
        meter = TurnMeter("a1")
        meter.start()
        meter.finish(record_duration=False)
        assert _active(reader) == 0
        assert metric_points(reader, "gen_ai.invoke_agent.duration") == []


def test_finish_without_start_never_goes_negative() -> None:
    with active_telemetry() as reader:
        TurnMeter("a1").finish()
        assert _active(reader) == 0


def test_decrement_uses_attributes_captured_at_start() -> None:
    from octop.infra.telemetry import bind_agent_repo

    class _Repo:
        def __init__(self) -> None:
            self.name = "Old"

        def get(self, _agent_id: str) -> object:
            return type("Row", (), {"name": self.name})()

    repo = _Repo()
    with active_telemetry() as reader:
        bind_agent_repo(repo)  # type: ignore[arg-type]
        meter = TurnMeter("a1")
        meter.start()
        repo.name = "New"
        # The name cache may expire mid-turn; the decrement must hit the same series.
        from octop.infra.telemetry import setup as _setup

        assert _setup._agent_names is not None
        _setup._agent_names._cache.clear()
        meter.finish(record_duration=False)
        points = metric_points(reader, "octop.turn.active")
    bind_agent_repo(None)
    assert [p.value for p in points] == [0]


def test_first_token_recorded_once_on_first_visible_text() -> None:
    with active_telemetry() as reader:
        meter = TurnMeter("a1", source="cron")
        meter.observe({"type": "state_update"})
        meter.observe({"type": "thinking", "content": "hmm"})
        meter.observe({"type": "token", "content": ""})
        assert metric_points(reader, "octop.turn.time_to_first_token") == []
        meter.observe({"type": "token", "content": "hi"})
        meter.observe({"type": "token", "content": " there"})
        meter.observe({"type": "delta", "text": "again"})
        (point,) = metric_points(reader, "octop.turn.time_to_first_token")
    assert point.count == 1
    assert point.attributes["octop.usage.source"] == "cron"
    assert point.attributes["gen_ai.agent.id"] == "a1"


def test_no_first_token_when_the_turn_never_produces_text() -> None:
    with active_telemetry() as reader:
        meter = TurnMeter("a1")
        meter.start()
        meter.observe({"type": "tool_call_chunk"})
        meter.finish(RuntimeError("boom"))
        assert metric_points(reader, "octop.turn.time_to_first_token") == []


def test_usage_tracker_forwards_chunks_to_its_meter() -> None:
    with active_telemetry() as reader:
        tracker = UsageTracker(meter=TurnMeter("a1"))
        tracker.observe({"type": "token", "content": "x"})
        (point,) = metric_points(reader, "octop.turn.time_to_first_token")
    assert point.count == 1


def test_meter_is_silent_when_telemetry_is_inactive() -> None:
    meter = TurnMeter("a1")
    meter.start()
    meter.observe({"type": "token", "content": "x"})
    meter.finish(RuntimeError("x"))
