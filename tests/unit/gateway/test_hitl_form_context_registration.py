"""Structured-form context must reach the store at registration time.

Durable stores INSERT the row inside ``register()``; assigning
``record.form_context`` afterwards only mutates a local object, so the value
never reaches PostgreSQL and ``cancel_pending_by_form_id`` cannot match it.
"""
from __future__ import annotations

from typing import Any

from octop.infra.gateway.hitl.coordinator import (
    HitlChannelCoordinator,
    HitlStreamContext,
)
from octop.infra.gateway.hitl.store import HitlPendingStore


class RecordingStore(HitlPendingStore):
    """In-memory store that remembers the kwargs of every ``register`` call."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[dict[str, Any]] = []

    def register(self, **kwargs: Any):  # type: ignore[override]
        self.calls.append(dict(kwargs))
        return super().register(**kwargs)


def _ctx(tag: str = "1") -> HitlStreamContext:
    return HitlStreamContext(
        thread_id=f"thread-{tag}",
        agent_id="agent-1",
        user_id=7,
        session_key=f"session-{tag}",
        channel_type="dashboard",
    )


def _form_request(form_id: str = "form-1", timeout: int | None = 600) -> dict:
    return {
        "action_requests": [
            {
                "name": "request_structured_form",
                "args": {
                    "form_id": form_id,
                    "schema_version": 1,
                    "timeout_seconds": timeout,
                    "context": {"case": "unit"},
                },
            }
        ]
    }


def test_coordinator_hands_form_context_to_register() -> None:
    store = RecordingStore()
    coord = HitlChannelCoordinator(store=store)

    record = coord.register_from_request(_form_request(), ctx=_ctx())

    assert store.calls, "register_from_request must call store.register"
    form_context = store.calls[-1]["form_context"]
    assert form_context["form_id"] == "form-1"
    assert form_context["schema_version"] == 1
    assert form_context["timeout_seconds"] == 600
    assert form_context["context"] == {"case": "unit"}
    assert record.form_context == form_context


def test_coordinator_sends_none_for_plain_tool_approval() -> None:
    store = RecordingStore()
    coord = HitlChannelCoordinator(store=store)

    coord.register_from_request(
        {"action_requests": [{"name": "run_shell", "args": {"cmd": "ls"}}]},
        ctx=_ctx(),
    )

    assert store.calls[-1]["form_context"] is None


def test_memory_store_accepts_form_context_keyword() -> None:
    store = HitlPendingStore()

    record = store.register(
        thread_id="thread-9",
        agent_id="agent-9",
        user_id=1,
        session_key="session-9",
        channel_type="dashboard",
        action_requests=[{"name": "request_structured_form", "args": {}}],
        review_configs=None,
        form_context={"form_id": "form-9", "timeout_seconds": 30},
    )

    assert record.form_context == {"form_id": "form-9", "timeout_seconds": 30}


def test_memory_store_refreshes_form_context_when_slot_is_reused() -> None:
    store = HitlPendingStore()
    kwargs = dict(
        thread_id="thread-r",
        agent_id="agent-r",
        user_id=1,
        session_key="session-r",
        channel_type="dashboard",
        action_requests=[{"name": "request_structured_form", "args": {}}],
        review_configs=None,
    )

    first = store.register(**kwargs, form_context={"form_id": "first"})
    again = store.register(**kwargs, form_context={"form_id": "second"})

    assert again.pending_id == first.pending_id
    assert again.form_context == {"form_id": "second"}
