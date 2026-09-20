"""Harness stream → trajectory event projection."""

from octop.infra.history.trajectory.projector import project_harness_chunk
from octop.infra.history.trajectory.types import TrajectoryEvent, TrajectoryKind

__all__ = ["TrajectoryEvent", "TrajectoryKind", "project_harness_chunk"]
