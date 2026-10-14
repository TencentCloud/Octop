"""Mid-turn steering types (issue #1300 soft boundary-drain)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

STEER_DEPTH_CAP = 8
STEER_CONTINUATION_CAP = 8
STEER_TEXT_CAP_BYTES = 200_000
STEER_DELIMITER = "\n---\n"
STEER_PREVIEW_CHARS = 200
# Steers parked across an HITL pause are dropped if the approval is never
# resolved (mirrors the HITL pending-store TTL horizon).
HITL_PARK_TTL_SECONDS = 30 * 60

TurnPhase = Literal[
    "streaming_text",
    "awaiting_tools",
    "between_model_steps",
    "hitl_paused",
    "cancelling",
    "compacting",
    "terminal",
    "idle",
]

GatewayRejectReason = Literal[
    "client_pending_id_required",
    "empty_input",
    "input_too_large",
    "forbidden",
]

HarnessRejectReason = Literal[
    "no_active_turn",
    "expected_turn_id_required",
    "expected_turn_id_mismatch",
    "turn_not_steerable",
    "turn_already_cancelled",
    "turn_active",
    "queue_full",
    "hitl_paused",
]

SteerRejectReason = GatewayRejectReason | HarnessRejectReason

GATEWAY_REJECT_REASONS: frozenset[str] = frozenset(
    {"client_pending_id_required", "empty_input", "input_too_large", "forbidden"}
)

STEERABLE_PHASES: frozenset[str] = frozenset(
    {"streaming_text", "awaiting_tools", "between_model_steps"}
)

Delivery = Literal["auto", "steer", "follow_up"]

DiscardReason = Literal[
    "turn_cancelled",
    "turn_failed",
    "continuation_exhausted",
    "hitl_paused",
]


@dataclass
class PendingSteer:
    client_pending_id: str
    pending_id: str
    text: str
    preview: str


@dataclass
class TurnSteerState:
    turn_id: str
    phase: TurnPhase = "streaming_text"
    queue: list[PendingSteer] = field(default_factory=list)
    continuation_count: int = 0
    # client_pending_id -> pending_id while queued; drained remembers message_id
    known: dict[str, str] = field(default_factory=dict)
    drained_message_ids: dict[str, str] = field(default_factory=dict)
    last_allocated_seq: int = 0
    # Wall-clock epoch seconds when an HITL pause parked this state.
    parked_at: float | None = None


@dataclass(frozen=True)
class SteerAdmitOk:
    status: Literal["queued", "idempotent"]
    turn_id: str
    pending_id: str
    client_pending_id: str
    queue_length: int
    message_id: str | None = None
    seq: int | None = None  # allocated only when a new queued event is emitted
    emit_queued: bool = False


@dataclass(frozen=True)
class SteerAdmitReject:
    status: Literal["rejected"] = "rejected"
    reason: SteerRejectReason = "turn_not_steerable"
    client_pending_id: str | None = None
    turn_id: str | None = None
    seq: int | None = None  # set for harness-class rejects
    gateway_class: bool = False


AdmitResult = SteerAdmitOk | SteerAdmitReject


def preview_text(text: str, *, limit: int = STEER_PREVIEW_CHARS) -> str:
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def utf8_len(text: str) -> int:
    return len(text.encode("utf-8"))


def queue_sum_bytes(items: list[PendingSteer], *, extra: str | None = None) -> int:
    texts = [item.text for item in items]
    if extra is not None:
        texts.append(extra)
    if not texts:
        return 0
    body = sum(utf8_len(t) for t in texts)
    overhead = max(0, len(texts) - 1) * utf8_len(STEER_DELIMITER)
    return body + overhead


def coalesce_texts(texts: list[str]) -> str:
    return STEER_DELIMITER.join(t.strip() for t in texts if t.strip())
