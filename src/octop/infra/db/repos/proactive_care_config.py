"""Data-access layer for the proactive care push configuration table.

The proactive_care_config table stores each agent's proactive care push
configuration, including active hours, push interval, and other parameters.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from octop.infra.db.pool import DatabasePool


@dataclass
class ProactiveCareConfig:
    """Proactive care push configuration."""

    agent_id: str
    enabled: bool = True
    active_hours_start: str = "09:00"  # HH:MM
    active_hours_end: str = "22:00"  # HH:MM
    min_interval_hours: int = 5
    max_interval_hours: int = 24


_DEFAULT_CONFIG = ProactiveCareConfig(agent_id="")


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
                "SELECT enabled, active_hours_start, active_hours_end, "
                "min_interval_hours, max_interval_hours "
                "FROM proactive_care_config WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()
        if row is None:
            return ProactiveCareConfig(agent_id=agent_id)
        return ProactiveCareConfig(
            agent_id=agent_id,
            enabled=bool(row[0]),
            active_hours_start=row[1],
            active_hours_end=row[2],
            min_interval_hours=row[3],
            max_interval_hours=row[4],
        )

    def upsert(self, config: ProactiveCareConfig) -> None:
        """Save or update the agent's proactive care configuration.

        Args:
            config: The configuration to save.
        """
        now = int(time.time())
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO proactive_care_config "
                "(agent_id, enabled, active_hours_start, active_hours_end, "
                "min_interval_hours, max_interval_hours, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(agent_id) DO UPDATE SET "
                "enabled = excluded.enabled, "
                "active_hours_start = excluded.active_hours_start, "
                "active_hours_end = excluded.active_hours_end, "
                "min_interval_hours = excluded.min_interval_hours, "
                "max_interval_hours = excluded.max_interval_hours, "
                "updated_at = excluded.updated_at",
                (
                    config.agent_id,
                    int(config.enabled),
                    config.active_hours_start,
                    config.active_hours_end,
                    config.min_interval_hours,
                    config.max_interval_hours,
                    now,
                ),
            )

    def list_enabled(self) -> list[ProactiveCareConfig]:
        """List the configurations of all agents that have proactive care push enabled.

        Returns:
            The list of enabled ProactiveCareConfig.
        """
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT agent_id, enabled, active_hours_start, active_hours_end, "
                "min_interval_hours, max_interval_hours "
                "FROM proactive_care_config WHERE enabled = 1",
            ).fetchall()
        return [
            ProactiveCareConfig(
                agent_id=row[0],
                enabled=bool(row[1]),
                active_hours_start=row[2],
                active_hours_end=row[3],
                min_interval_hours=row[4],
                max_interval_hours=row[5],
            )
            for row in rows
        ]
