"""Data-access layer for the proactive care push configuration table.

The proactive_care_config table stores each agent's proactive care push
configuration, including active hours, push interval, and other parameters.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow


@dataclass
class ProactiveCareConfig:
    """Proactive care push configuration."""

    agent_id: str
    enabled: bool = True
    active_hours_start: str = "09:00"  # HH:MM
    active_hours_end: str = "22:00"  # HH:MM
    min_interval_hours: int = 5
    max_interval_hours: int = 24

    model_ref: str | None = None
    reasoning_effort: str = "auto"
    generation_timeout_seconds: int = 30

    @classmethod
    def from_row(cls, agent_id: str, row: DbRow) -> ProactiveCareConfig:
        return cls(
            agent_id=agent_id,
            enabled=bool(row["enabled"]),
            active_hours_start=row["active_hours_start"],
            active_hours_end=row["active_hours_end"],
            min_interval_hours=row["min_interval_hours"],
            max_interval_hours=row["max_interval_hours"],
            model_ref=row["model_ref"],
            reasoning_effort=row["reasoning_effort"],
            generation_timeout_seconds=row["generation_timeout_seconds"],
        )


class ProactiveCareConfigRepo:
    """Data-access object for the proactive_care_config table."""

    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def get(self, agent_id: str) -> ProactiveCareConfig:
        """Read the agent's proactive care configuration, returning defaults if not configured.

        Args:
            agent_id: The agent ID.

        Returns:
            A ProactiveCareConfig; returns the default when not configured.
        """
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM proactive_care_config WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()
        if row is None:
            return ProactiveCareConfig(agent_id=agent_id)
        return ProactiveCareConfig.from_row(agent_id, row)

    def upsert(
        self, config: ProactiveCareConfig, *, generation_fields: set[str] | None = None
    ) -> None:
        """Keep generation settings omitted by older clients on an existing row."""
        columns = [
            "enabled",
            "active_hours_start",
            "active_hours_end",
            "min_interval_hours",
            "max_interval_hours",
            "updated_at",
        ]
        for field in ("model_ref", "reasoning_effort", "generation_timeout_seconds"):
            if generation_fields is None or field in generation_fields:
                columns.append(field)
        updates = ", ".join(f"{column} = excluded.{column}" for column in columns)
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO proactive_care_config "
                "(agent_id, enabled, active_hours_start, active_hours_end, "
                "min_interval_hours, max_interval_hours, updated_at, model_ref, "
                "reasoning_effort, generation_timeout_seconds) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                f"ON CONFLICT(agent_id) DO UPDATE SET {updates}",
                (
                    config.agent_id,
                    int(config.enabled),
                    config.active_hours_start,
                    config.active_hours_end,
                    config.min_interval_hours,
                    config.max_interval_hours,
                    int(time.time()),
                    config.model_ref,
                    config.reasoning_effort,
                    config.generation_timeout_seconds,
                ),
            )

    def list_enabled(self) -> list[ProactiveCareConfig]:
        """List proactive-care configs for every enabled agent that should be scheduled.

        Agents without a ``proactive_care_config`` row use the same defaults as
        ``get()`` (enabled=True). An explicit ``enabled=0`` row opts out.
        Disabled agents (``agents.enabled = 0``) are excluded.

        Returns:
            The list of enabled ProactiveCareConfig.
        """
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT a.agent_id AS scheduled_agent_id, c.* "
                "FROM agents a "
                "LEFT JOIN proactive_care_config c ON c.agent_id = a.agent_id "
                "WHERE a.enabled = 1 AND (c.agent_id IS NULL OR c.enabled = 1)",
            ).fetchall()
        return [
            ProactiveCareConfig.from_row(row["scheduled_agent_id"], row)
            if row["enabled"] is not None
            else ProactiveCareConfig(agent_id=row["scheduled_agent_id"])
            for row in rows
        ]
