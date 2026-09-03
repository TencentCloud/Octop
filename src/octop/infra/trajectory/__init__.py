"""Harness stream → trajectory event projection."""

from octop.infra.trajectory.projector import project_harness_chunk
from octop.infra.trajectory.types import TrajectoryEvent, TrajectoryKind

__all__ = ["TrajectoryEvent", "TrajectoryKind", "project_harness_chunk"]
