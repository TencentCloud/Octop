"""In-memory metrics counters."""

from __future__ import annotations

import contextlib
import threading
from dataclasses import dataclass, field


@dataclass
class Metrics:
    messages_total: int = 0
    stream_errors_total: int = 0
    cron_runs_total: int = 0
    cron_errors_total: int = 0
    agent_active: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def inc(self, name: str, n: int = 1, **labels: str) -> None:
        """Bump a counter; ``labels`` (e.g. ``channel_type``) only reach OpenTelemetry."""
        with self._lock:
            setattr(self, name, getattr(self, name) + n)
        with contextlib.suppress(Exception):
            from octop.infra.telemetry import record_counter  # noqa: PLC0415

            record_counter(name, n, **labels)

    def set(self, name: str, value: int) -> None:
        with self._lock:
            setattr(self, name, value)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "messages_total": self.messages_total,
                "stream_errors_total": self.stream_errors_total,
                "cron_runs_total": self.cron_runs_total,
                "cron_errors_total": self.cron_errors_total,
                "agent_active": self.agent_active,
            }


METRICS = Metrics()
