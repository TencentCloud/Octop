"""In-process binding: which adb device the agent may control.

Bound automatically for the duration of an active Remote Phone stream
session (same idea as an open browser / desktop session).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class MobileAgentControl:
    """Host-wide Remote Android agent binding (one active phone at a time)."""

    enabled: bool = False
    device: str | None = None


_lock = threading.Lock()
_state = MobileAgentControl()


def get_mobile_agent_control() -> MobileAgentControl:
    with _lock:
        return _state


def set_mobile_agent_control(*, enabled: bool, device: str | None) -> MobileAgentControl:
    """Enable/disable agent control for a concrete adb serial.

    Enabling requires a non-empty ``device``. Disabling clears the binding.
    Prefer letting the mobile stream websocket set this for the session lifetime.
    """
    global _state
    serial = (device or "").strip() or None
    if enabled and not serial:
        raise ValueError("device is required when enabling agent control")
    with _lock:
        _state = MobileAgentControl(
            enabled=bool(enabled),
            device=serial if enabled else None,
        )
        return _state


def clear_mobile_agent_control_if_device(device: str) -> None:
    """Drop the binding when the bound device's stream ends."""
    global _state
    serial = (device or "").strip()
    if not serial:
        return
    with _lock:
        if _state.device == serial:
            _state = MobileAgentControl()
