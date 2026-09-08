"""Per-agent trajectory flag and persist clipping."""

from __future__ import annotations

from octop.infra.trajectory.settings import (
    PAYLOAD_MAX_CHARS,
    SUMMARY_MAX_CHARS,
    agent_trajectory_enabled,
    apply_enable_trajectory,
    clip_persisted_event,
    clip_text,
)
from octop.infra.trajectory.types import TrajectoryEvent


def test_agent_trajectory_enabled_defaults_on_and_allows_explicit_opt_out() -> None:
    assert agent_trajectory_enabled(None) is True
    assert agent_trajectory_enabled({}) is True
    assert agent_trajectory_enabled({"enable_trajectory": False}) is False
    assert agent_trajectory_enabled({"enable_trajectory": "true"}) is True
    assert agent_trajectory_enabled({"enable_trajectory": True}) is True


def test_apply_enable_trajectory_omits_default_on() -> None:
    cfg: dict[str, object] = {"backend": {"type": "local"}}
    apply_enable_trajectory(cfg, False)
    assert cfg["enable_trajectory"] is False
    apply_enable_trajectory(cfg, True)
    assert "enable_trajectory" not in cfg


def test_clip_persisted_event_bounds_summary_and_payload() -> None:
    event = TrajectoryEvent(
        event_id="e",
        thread_id="T",
        agent_id="A",
        seq=1,
        ts=1.0,
        kind="assistant",
        turn_id=None,
        request_seq=None,
        is_error=False,
        summary="s" * (SUMMARY_MAX_CHARS + 10),
        payload={"content": "c" * (PAYLOAD_MAX_CHARS + 10)},
    )
    clipped = clip_persisted_event(event)
    assert len(clipped.summary) <= SUMMARY_MAX_CHARS
    assert len(str(clipped.payload["content"])) <= PAYLOAD_MAX_CHARS
    assert clip_text("ab", 2) == "ab"
    assert clip_text("abc", 2).endswith("…")
