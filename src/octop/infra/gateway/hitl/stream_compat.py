"""Recover HITL interrupts dropped by octop-harness on LangGraph astream v2.

LangGraph v2 moves ``__interrupt__`` off the values payload onto
``chunk["interrupts"]``. Harness ``_project_chunk`` only reads
``data["__interrupt__"]`` on updates, so ``hitl_required`` never reaches
Octop and the dashboard leaves ``ask_user_question`` spinning.
"""

from __future__ import annotations

from typing import Any

from octop.infra.gateway.hitl.format import normalize_hitl_request

_INSTALLED = False


def hitl_events_from_interrupts(interrupts: Any) -> list[dict[str, Any]]:
    """Project LangGraph interrupt items into harness ``hitl_required`` chunks."""
    if not interrupts:
        return []
    if not isinstance(interrupts, (list, tuple)):
        interrupts = (interrupts,)
    out: list[dict[str, Any]] = []
    for item in interrupts:
        value: Any = item
        if isinstance(item, dict):
            value = item.get("value", item)
        elif hasattr(item, "value"):
            value = item.value
        request = normalize_hitl_request(value)
        if not request.get("action_requests"):
            continue
        out.append({"type": "hitl_required", "request": request})
    return out


def _hitl_has_actions(event: dict[str, Any]) -> bool:
    if event.get("type") != "hitl_required":
        return False
    request = event.get("request")
    return isinstance(request, dict) and bool(request.get("action_requests"))


def merge_hitl_projection(
    events: list[dict[str, Any]],
    interrupts: Any,
) -> list[dict[str, Any]]:
    """Unwrap existing ``hitl_required`` events and fill from v2 interrupts if empty."""
    extra = hitl_events_from_interrupts(interrupts)
    for event in events:
        if event.get("type") != "hitl_required":
            continue
        request = event.get("request")
        if isinstance(request, dict):
            event["request"] = normalize_hitl_request(request)
    if extra and not any(_hitl_has_actions(event) for event in events):
        events = [event for event in events if event.get("type") != "hitl_required"]
        events = [*events, *extra]
    return events


def install_harness_hitl_compat() -> None:
    """Patch harness stream projection so v2 interrupts become ``hitl_required``."""
    global _INSTALLED
    if _INSTALLED:
        return
    from octop_harness.protocols.langgraph import LangGraphProtocol

    original = LangGraphProtocol._project_chunk

    def _project_chunk(self: Any, chunk: Any, splitter: Any) -> list[dict[str, Any]]:
        events = original(self, chunk, splitter)
        if isinstance(chunk, dict):
            events = merge_hitl_projection(events, chunk.get("interrupts"))
        return events

    LangGraphProtocol._project_chunk = _project_chunk  # type: ignore[method-assign]
    _INSTALLED = True


__all__ = [
    "hitl_events_from_interrupts",
    "install_harness_hitl_compat",
    "merge_hitl_projection",
]
