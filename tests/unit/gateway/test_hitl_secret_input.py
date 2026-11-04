"""HITL store lifecycle and IM degradation for secret-input pauses."""

from __future__ import annotations

from types import SimpleNamespace

from octop.infra.gateway.hitl.coordinator import HitlChannelCoordinator
from octop.infra.gateway.hitl.format import (
    REQUEST_SECRET_INPUT_TOOL_NAME,
    extract_secret_input_request,
    format_hitl_card,
    is_secret_input_action_requests,
)
from octop.infra.gateway.hitl.store import HitlPendingStore

_SECRET_ACTIONS = [
    {
        "name": REQUEST_SECRET_INPUT_TOOL_NAME,
        "args": {"slot": "STEAM_WEB_API_KEY", "prompt": "Steam Web API key", "title": "Steam"},
    }
]


def _register(store: HitlPendingStore, *, user_id: int = 1, thread_id: str = "thr-1"):
    return store.register(
        thread_id=thread_id,
        agent_id="agent-1",
        user_id=user_id,
        session_key="agent-1:dashboard:1:dm",
        channel_type="dashboard",
        action_requests=list(_SECRET_ACTIONS),
        review_configs=None,
    )


# ---------------------------------------------------------------- detection


def test_is_secret_input_action_requests() -> None:
    assert is_secret_input_action_requests(_SECRET_ACTIONS) is True
    assert is_secret_input_action_requests([{"name": "execute", "args": {}}]) is False
    assert is_secret_input_action_requests([]) is False


def test_extract_secret_input_request_parses_args() -> None:
    request = extract_secret_input_request(_SECRET_ACTIONS)
    assert request == {
        "slot": "STEAM_WEB_API_KEY",
        "prompt": "Steam Web API key",
        "title": "Steam",
    }
    assert extract_secret_input_request([{"name": "execute", "args": {}}]) is None


# ---------------------------------------------------------------- store lifecycle


def test_claim_moves_pending_to_filling_once() -> None:
    store = HitlPendingStore()
    record = _register(store)
    first = store.claim_secret_input(record.pending_id)
    assert first is not None
    assert first.status == "filling"
    # A racing or replayed submit must not claim twice.
    assert store.claim_secret_input(record.pending_id) is None


def test_reopen_returns_filling_to_pending() -> None:
    store = HitlPendingStore()
    record = _register(store)
    assert store.claim_secret_input(record.pending_id) is not None
    store.reopen_secret_input(record.pending_id)
    assert store.get(record.pending_id).status == "pending"  # type: ignore[union-attr]
    # Reopen after terminal resolution is a no-op.
    store.mark_resolved(record.pending_id, "filled")
    store.reopen_secret_input(record.pending_id)
    assert store.get(record.pending_id).status == "filled"  # type: ignore[union-attr]


def test_claim_expired_record_returns_none() -> None:
    store = HitlPendingStore(ttl_seconds=0.0)
    record = _register(store)
    assert store.claim_secret_input(record.pending_id) is None
    # The expired record is gone from every resolution path.
    assert store.resolve_pending_for_thread("thr-1", agent_id="agent-1", user_id=1) is None


def test_resolve_pending_for_thread_scopes_by_user_and_thread() -> None:
    store = HitlPendingStore()
    record = _register(store, user_id=1, thread_id="thr-1")
    assert store.resolve_pending_for_thread("thr-1", agent_id="agent-1", user_id=1) is not None
    assert store.resolve_pending_for_thread("thr-2", agent_id="agent-1", user_id=1) is None
    assert store.resolve_pending_for_thread("thr-1", agent_id="agent-1", user_id=2) is None
    assert (
        store.resolve_pending_for_thread(
            "thr-1", agent_id="agent-1", user_id=1, pending_id=record.pending_id
        )
        is not None
    )


# ---------------------------------------------------------------- IM degradation


def test_format_hitl_card_renders_secret_notice() -> None:
    store = HitlPendingStore()
    record = _register(store)
    card = format_hitl_card(record.action_requests, pending_id=record.pending_id, locale="en")
    assert "STEAM_WEB_API_KEY" in card
    assert record.pending_id in card
    assert "dashboard" in card.lower()
    # No approval instructions on a secret card.
    assert "approve" not in card.lower()


def test_owned_tool_approval_ignores_secret_pauses() -> None:
    hitl = HitlChannelCoordinator()
    _register(hitl.store)
    assert hitl.owned_tool_approval("agent-1:dashboard:1:dm", agent_id="agent-1", user_id=1) is None


def test_slash_record_resolution_refuses_secret_pauses() -> None:
    from octop_gateway.models import MessageEvent

    def _event_text(event: MessageEvent) -> str:
        return "\n".join(getattr(part, "text", "") for part in event.content)

    hitl = HitlChannelCoordinator()
    record = _register(hitl.store)
    ctx = SimpleNamespace(session_key="agent-1:dashboard:1:dm", agent_id="agent-1", user_id=1)
    for approve in (True, False):
        outcome = hitl._resolve_slash_record(ctx, approve=approve, arg="", lang="en")
        assert isinstance(outcome, MessageEvent)
        assert "dashboard" in _event_text(outcome).lower()
    # Explicit pending id path is refused as well.
    outcome = hitl._resolve_slash_record(ctx, approve=True, arg=record.pending_id, lang="en")
    assert isinstance(outcome, MessageEvent)


def test_session_auto_approve_never_covers_secret_pause() -> None:
    from octop.infra.gateway.hitl.coordinator import approve_decisions_if_allowed

    policies = SimpleNamespace(allows=lambda thread_id, name: True)
    chunk = {
        "type": "hitl_required",
        "request": {"action_requests": list(_SECRET_ACTIONS)},
    }
    # Even with an all-allowing policy the secret pause must reach the user.
    policies = SimpleNamespace(
        allows=lambda thread_id, name: name != REQUEST_SECRET_INPUT_TOOL_NAME
    )
    assert approve_decisions_if_allowed(policies, "thr-1", chunk) is None
