"""Settings for record/replay."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from octop_browser.settings import state_dir


def _env_path(key: str, default: Path) -> Path:
    val = os.environ.get(key)
    return Path(val).expanduser() if val else default


def _env_int(key: str, default: int) -> int:
    val = os.environ.get(key)
    return int(val) if val else default


@dataclass
class RecordReplaySettings:
    base_dir: Path = field(
        default_factory=lambda: _env_path(
            "BROWSER_RECORD_REPLAY_DIR",
            state_dir() / "record-replay",
        )
    )
    max_event_bytes: int = field(
        default_factory=lambda: _env_int("BROWSER_RECORD_MAX_EVENT_BYTES", 65536)
    )
    max_events_per_second: int = field(
        default_factory=lambda: _env_int("BROWSER_RECORD_MAX_EVENTS_PER_SECOND", 100)
    )


settings = RecordReplaySettings()
