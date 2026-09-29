"""Per-agent memory dashboard router.

Mounts at ``/api/agents/{agent_id}/memory/*`` and forwards each
endpoint to a single JSON-RPC method on the agent's
``octop_memory.Bridge``. The router itself contains no business
logic — every handler is one ``call_memory_rpc(...)`` call.

Surface (mirrors the design doc §6.2):

* ``POST .../atoms/list``                       → ``list_atoms``
* ``GET  .../atoms/{atom_id}``                  → ``memory_get`` (path projection)
* ``POST .../atoms``                            → ``create_atom``
* ``POST .../atoms/{atom_id}:replace``          → ``replace_atom``
* ``POST .../atoms/{atom_id}:deprecate``        → ``deprecate_atom``
* ``POST .../entities/list``                    → ``list_entities``
* ``GET  .../entities/{entity_id}``             → ``memory_get`` (page projection, may be empty)
* ``POST .../episodes/list``                    → ``list_episodes``
* ``POST .../journal/list``                     → ``list_journal``
* ``POST .../candidates/list``                  → ``list_candidates``
* ``GET  .../raw_events/{event_id}``            → ``get_raw_event``
* ``GET  .../candidates/{candidate_id}``        → ``get_candidate``
* ``POST .../candidates/{id}:promote``          → ``promote_candidate``
* ``POST .../candidates/{id}:reject``           → ``reject_candidate``
* ``GET  .../stats/counts``                     → ``stats_counts``
* ``GET  .../stats/growth?days=N``              → ``stats_growth``
* ``GET  .../stats/atom_kinds``                 → ``stats_atom_kinds``
* ``GET  .../journal/recent?limit=N``           → ``recent_journal``
* ``GET  .../terminal/about_me?limit=N``        → ``terminal_about_me``
* ``GET  .../terminal/current_focus``           → ``terminal_current_focus``
* ``GET  .../terminal/things_you_told_me``      → ``terminal_things_you_told_me``
* ``GET  .../terminal/recent_stories``          → ``terminal_recent_stories``
* ``GET  .../terminal/entities``                → ``terminal_entities``
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal, cast

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from octop.api.common.agent import assert_agent_owner, require_agent_owner_row
from octop.api.common.agent_workspace import resolve_agent_workspace_dir
from octop.api.common.memory_client import call_memory_rpc
from octop.api.deps import current_user, get_server
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.projects.service import PROJECT_WRITE, ProjectActor, ProjectService
from octop.infra.users.identity import User

logger = logging.getLogger(__name__)

router = APIRouter()

# Defaults mirror ``HarnessAgentConfig`` (octop_harness.config). Kept in sync
# manually — the dashboard writes these into the agent's ``config_json`` under
# the ``memory`` section, and ``AgentManager._build_harness_config`` reads them
# back when constructing the agent.
_EXTRACT_DEFAULTS: dict[str, Any] = {
    "memory_enabled": True,
    "extract_on_session_end": True,
    "extract_trigger_mode": "idle",
    "extract_idle_seconds": 300.0,
    "extract_interval_seconds": 21600.0,
    # Model ref ("provider/model") used for extraction / promotion; None → AUTO
    # (follow the agent's effective chat model).
    "aux_model": None,
}
# Guard rails so a bad UI value can't schedule a hot loop or a never-firing timer.
_MIN_IDLE_SECONDS = 60.0  # UI minimum: one minute; zero must not disable extraction
_MIN_INTERVAL_SECONDS = 300.0  # 5 min floor for the fixed-interval sweep
_MAX_SECONDS = 7 * 24 * 3600.0  # 7 days


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class _ListAtomsBody(BaseModel):
    """Request body for ``POST .../atoms/list``.

    Mirrors the bridge ``list_atoms`` params. All fields optional.
    """

    entity_id: str | None = None
    candidate_type: str | None = Field(
        default=None,
        description="One of Fact / Decision / Task / Preference / ConflictCandidate",
    )
    importance_min: str | None = Field(default=None, description="low / medium / high")
    include_deprecated: bool = False
    query: str | None = None
    order_by: str | None = Field(default=None, description="created_at / occurred_at / importance")
    order: str | None = Field(default=None, description="asc / desc")
    offset: int | None = None
    limit: int | None = None


class _ListRawEventsBody(BaseModel):
    """Request body for ``POST .../raw_events/list``.

    Mirrors the bridge ``list_raw_events`` params. All fields optional.
    """

    session_id: str | None = None
    thread_id: str | None = None
    event_type: str | None = Field(
        default=None,
        description="One of user_message / assistant_message / tool_call / tool_result / ...",
    )
    query: str | None = None
    offset: int | None = None
    limit: int | None = None


class _ListEntitiesBody(BaseModel):
    entity_type: str | None = None
    query: str | None = None
    order_by: str | None = None
    order: str | None = None
    offset: int | None = None
    limit: int | None = None


class _ListEpisodesBody(BaseModel):
    emotion: str | None = None
    intensity_min: int | None = Field(default=None, ge=1, le=5)
    date_from: str | None = None
    date_to: str | None = None
    topic: str | None = None
    query: str | None = None
    offset: int | None = None
    limit: int | None = None


class _ListJournalBody(BaseModel):
    action: str | None = None
    target_type: str | None = Field(default=None, description="atom / entity / candidate")
    actor: str | None = None
    time_from: str | None = None
    time_to: str | None = None
    target_entity_id: str | None = None
    target_atom_id: str | None = None
    target_candidate_id: str | None = None
    offset: int | None = None
    limit: int | None = None


class _ListCandidatesBody(BaseModel):
    """Request body for ``POST .../candidates/list``.

    Mirrors the bridge ``list_candidates`` params. All fields optional;
    the bridge defaults ``status`` to ``pending`` so the empty body
    returns the work queue.
    """

    status: str | None = Field(
        default=None,
        description="pending / needs_review / conflict / promoted / rejected",
    )
    candidate_type: str | None = Field(
        default=None,
        description="One of Fact / Decision / Task / Preference / ConflictCandidate",
    )
    session_id: str | None = None
    target_entity_id: str | None = None
    time_from: str | None = None
    time_to: str | None = None
    query: str | None = None
    offset: int | None = None
    limit: int | None = None


class _ExtractConfigBody(BaseModel):
    """Request body for ``PUT .../memory/extract-config``.

    Controls when L0→L2/L3 distillation runs automatically. ``trigger_mode``
    selects the (mutually exclusive) cadence; the matching seconds field
    applies. All fields optional — omitted fields keep their stored value.
    """

    memory_enabled: bool | None = None
    extract_on_session_end: bool | None = None
    extract_trigger_mode: str | None = Field(default=None, description="idle / interval")
    extract_idle_seconds: float | None = Field(
        default=None, description="mode=idle: seconds of inactivity before extract"
    )
    extract_interval_seconds: float | None = Field(
        default=None, description="mode=interval: seconds between sweeps"
    )
    aux_model: str | None = Field(
        default=None,
        description="'provider/model' ref for extraction; '' resets to AUTO",
    )


class _RejectCandidateBody(BaseModel):
    reason: str | None = None
    actor: str | None = Field(default=None, description="user / auto / rule (defaults user)")


class _PromoteCandidateBody(BaseModel):
    """Adoption target (T-50).

    Omitted ⇒ the pre-existing behaviour: the candidate is adopted into the
    agent's own private layer ``agent_{agent_id}`` through exactly the same
    single ``call_memory_rpc`` the two-argument client already made.
    """

    project_id: str | None = Field(
        default=None,
        description="Adopt into project_{project_id} instead of the agent's private layer",
    )


class _RecordToProjectBody(BaseModel):
    """Target of 「记到项目」 (T-50; PLAN 「写入路径」 row 4)."""

    project_id: str = Field(description="Target project; write access is checked on it")


class _DeprecateAtomBody(BaseModel):
    reason: str | None = None
    actor: str | None = None


class _CreateAtomBody(BaseModel):
    assertion: str
    entity_id: str | None = None
    entity_name: str | None = None
    entity_type: str | None = Field(
        default=None, description="User / Person / Project / Decision / Task / Fact"
    )
    kind: str | None = Field(default=None, description="Fact / Decision / Task / Preference")
    importance: str | None = None
    confidence: str | None = None
    reason: str | None = None


class _ReplaceAtomBody(BaseModel):
    assertion: str
    reason: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_none(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove ``None`` keys before forwarding so the bridge sees a clean dict.

    The bridge handlers treat ``None`` and "missing" identically; we
    drop them to keep the payload smaller and to avoid surprising
    handler validation that special-cases ``param is None``.
    """
    return {k: v for k, v in payload.items() if v is not None}


# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------


@router.post("/agents/{agent_id}/memory/atoms/list")
async def list_atoms(
    agent_id: str,
    body: _ListAtomsBody = Body(default_factory=_ListAtomsBody),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        call_memory_rpc(
            agent_id=agent_id,
            method="list_atoms",
            params=_strip_none(body.model_dump()),
            user=user,
            as_user=as_user,
            server=server,
        ),
    )


@router.post("/agents/{agent_id}/memory/raw_events/list")
async def list_raw_events(
    agent_id: str,
    body: _ListRawEventsBody = Body(default_factory=_ListRawEventsBody),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        call_memory_rpc(
            agent_id=agent_id,
            method="list_raw_events",
            params=_strip_none(body.model_dump()),
            user=user,
            as_user=as_user,
            server=server,
        ),
    )


@router.post("/agents/{agent_id}/memory/entities/list")
async def list_entities(
    agent_id: str,
    body: _ListEntitiesBody = Body(default_factory=_ListEntitiesBody),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        call_memory_rpc(
            agent_id=agent_id,
            method="list_entities",
            params=_strip_none(body.model_dump()),
            user=user,
            as_user=as_user,
            server=server,
        ),
    )


@router.post("/agents/{agent_id}/memory/episodes/list")
async def list_episodes(
    agent_id: str,
    body: _ListEpisodesBody = Body(default_factory=_ListEpisodesBody),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        call_memory_rpc(
            agent_id=agent_id,
            method="list_episodes",
            params=_strip_none(body.model_dump()),
            user=user,
            as_user=as_user,
            server=server,
        ),
    )


@router.post("/agents/{agent_id}/memory/journal/list")
async def list_journal(
    agent_id: str,
    body: _ListJournalBody = Body(default_factory=_ListJournalBody),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        call_memory_rpc(
            agent_id=agent_id,
            method="list_journal",
            params=_strip_none(body.model_dump()),
            user=user,
            as_user=as_user,
            server=server,
        ),
    )


@router.post("/agents/{agent_id}/memory/candidates/list")
async def list_candidates(
    agent_id: str,
    body: _ListCandidatesBody = Body(default_factory=_ListCandidatesBody),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        call_memory_rpc(
            agent_id=agent_id,
            method="list_candidates",
            params=_strip_none(body.model_dump()),
            user=user,
            as_user=as_user,
            server=server,
        ),
    )


# ---------------------------------------------------------------------------
# Single-row fetches
# ---------------------------------------------------------------------------


@router.get("/agents/{agent_id}/memory/raw_events/{event_id}")
async def get_raw_event(
    agent_id: str,
    event_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        call_memory_rpc(
            agent_id=agent_id,
            method="get_raw_event",
            params={"event_id": event_id},
            user=user,
            as_user=as_user,
            server=server,
        ),
    )


@router.get("/agents/{agent_id}/memory/candidates/{candidate_id}")
async def get_candidate(
    agent_id: str,
    candidate_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        call_memory_rpc(
            agent_id=agent_id,
            method="get_candidate",
            params={"candidate_id": candidate_id},
            user=user,
            as_user=as_user,
            server=server,
        ),
    )


@router.get("/agents/{agent_id}/memory/atoms/{atom_id}")
async def get_atom(
    agent_id: str,
    atom_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        call_memory_rpc(
            agent_id=agent_id,
            method="get_atom",
            params={"atom_id": atom_id},
            user=user,
            as_user=as_user,
            server=server,
        ),
    )


@router.get("/agents/{agent_id}/memory/entities/{entity_id}")
async def get_entity(
    agent_id: str,
    entity_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        call_memory_rpc(
            agent_id=agent_id,
            method="get_entity",
            params={"entity_id": entity_id},
            user=user,
            as_user=as_user,
            server=server,
        ),
    )


@router.get("/agents/{agent_id}/memory/episodes/{episode_id}")
async def get_episode(
    agent_id: str,
    episode_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        call_memory_rpc(
            agent_id=agent_id,
            method="get_episode",
            params={"episode_id": episode_id},
            user=user,
            as_user=as_user,
            server=server,
        ),
    )


# ---------------------------------------------------------------------------
# Stats / overview
# ---------------------------------------------------------------------------


@router.get("/agents/{agent_id}/memory/stats/counts")
async def stats_counts(
    agent_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        call_memory_rpc(
            agent_id=agent_id,
            method="stats_counts",
            params={},
            user=user,
            as_user=as_user,
            server=server,
        ),
    )


@router.get("/agents/{agent_id}/memory/stats/growth")
async def stats_growth(
    agent_id: str,
    days: int = Query(default=7, ge=1, le=90),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        call_memory_rpc(
            agent_id=agent_id,
            method="stats_growth",
            params={"days": days},
            user=user,
            as_user=as_user,
            server=server,
        ),
    )


@router.get("/agents/{agent_id}/memory/stats/atom_kinds")
async def stats_atom_kinds(
    agent_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        call_memory_rpc(
            agent_id=agent_id,
            method="stats_atom_kinds",
            params={},
            user=user,
            as_user=as_user,
            server=server,
        ),
    )


@router.get("/agents/{agent_id}/memory/journal/recent")
async def recent_journal(
    agent_id: str,
    limit: int = Query(default=5, ge=1, le=100),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        call_memory_rpc(
            agent_id=agent_id,
            method="recent_journal",
            params={"limit": limit},
            user=user,
            as_user=as_user,
            server=server,
        ),
    )


# ---------------------------------------------------------------------------
# Write actions
# ---------------------------------------------------------------------------


@router.post("/agents/{agent_id}/memory/candidates/{candidate_id}:promote")
async def promote_candidate(
    agent_id: str,
    candidate_id: str,
    body: _PromoteCandidateBody = Body(default_factory=_PromoteCandidateBody),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Adopt a candidate — into the agent's private layer, or into a project layer.

    Without ``project_id`` this is the pre-existing call, byte for byte: one
    ``promote_candidate`` RPC on the agent's own store, so the two-argument
    client shape (and its test) is untouched.

    With ``project_id`` the candidate is copied into ``project_{project_id}`` and
    adopted **there** through the same library operation (T-50). The gate is the
    project's **write** action — not its read action: SPEC B38 keeps the two
    separate, so a ``viewer`` (who may read the project) is refused here while a
    ``member`` / ``admin`` / ``owner`` succeeds.
    """
    if body.project_id is None:
        return cast(
            dict[str, Any],
            call_memory_rpc(
                agent_id=agent_id,
                method="promote_candidate",
                params={"candidate_id": candidate_id},
                user=user,
                as_user=as_user,
                server=server,
            ),
        )

    require_agent_owner_row(agent_id, user=user, as_user=as_user, server=server)
    project = _project_write_target(server, user=user, project_id=body.project_id)
    recall = _open_recall(server, agent_id, team_id=None)
    try:
        from octop.infra.agents.memory.project_writes import (  # noqa: PLC0415 - lazy, optional dep
            promote_candidate_into_project,
        )

        return promote_candidate_into_project(
            recall=recall,
            project_id=project.id,
            project_namespace=project.memory_namespace,
            candidate_id=candidate_id,
        )
    finally:
        recall.close()


@router.post("/agents/{agent_id}/memory/atoms/{atom_id}:record-to-project")
async def record_atom_to_project(
    agent_id: str,
    atom_id: str,
    body: _RecordToProjectBody,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Copy one existing memory from the agent layer into ``project_{project_id}``.

    PLAN 「写入路径」 row 4 (显式「记到项目」). The gate is the project's **write**
    action (SPEC B38) — reading the project's memory does not imply being allowed
    to move a memory into it. Idempotent: a row already present in the project
    layer is reported with ``recorded=false`` instead of being written twice.
    """
    require_agent_owner_row(agent_id, user=user, as_user=as_user, server=server)
    project = _project_write_target(server, user=user, project_id=body.project_id)
    recall = _open_recall(server, agent_id, team_id=None)
    try:
        from octop.infra.agents.memory.project_writes import (  # noqa: PLC0415 - lazy, optional dep
            record_atom_into_project,
        )

        return record_atom_into_project(
            recall=recall,
            project_id=project.id,
            project_namespace=project.memory_namespace,
            atom_id=atom_id,
        )
    finally:
        recall.close()


@router.post("/agents/{agent_id}/memory/candidates/{candidate_id}:reject")
async def reject_candidate(
    agent_id: str,
    candidate_id: str,
    body: _RejectCandidateBody = Body(default_factory=_RejectCandidateBody),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    params = _strip_none({"candidate_id": candidate_id, **body.model_dump()})
    return cast(
        dict[str, Any],
        call_memory_rpc(
            agent_id=agent_id,
            method="reject_candidate",
            params=params,
            user=user,
            as_user=as_user,
            server=server,
        ),
    )


@router.post("/agents/{agent_id}/memory/atoms/{atom_id}:deprecate")
async def deprecate_atom(
    agent_id: str,
    atom_id: str,
    body: _DeprecateAtomBody = Body(default_factory=_DeprecateAtomBody),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    params = _strip_none({"atom_id": atom_id, **body.model_dump()})
    return cast(
        dict[str, Any],
        call_memory_rpc(
            agent_id=agent_id,
            method="deprecate_atom",
            params=params,
            user=user,
            as_user=as_user,
            server=server,
        ),
    )


@router.post(
    "/agents/{agent_id}/memory/atoms",
    summary="Create a long-term memory",
    description=(
        "Creates a canonical memory under an existing or new entity. The request is recorded as actor=user; clients "
        "cannot override the audit actor."
    ),
)
async def create_atom(
    agent_id: str,
    body: _CreateAtomBody,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        call_memory_rpc(
            agent_id=agent_id,
            method="create_atom",
            params=_strip_none(body.model_dump()),
            user=user,
            as_user=as_user,
            server=server,
        ),
    )


@router.post(
    "/agents/{agent_id}/memory/atoms/{atom_id}:replace",
    summary="Correct a long-term memory",
    description=(
        "Creates a successor Atom and supersedes the active Atom without creating a conversation event or extraction "
        "candidate. The request is recorded as actor=user; clients cannot override the audit actor."
    ),
)
async def replace_atom(
    agent_id: str,
    atom_id: str,
    body: _ReplaceAtomBody,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    params = _strip_none({"atom_id": atom_id, **body.model_dump()})
    return cast(
        dict[str, Any],
        call_memory_rpc(
            agent_id=agent_id,
            method="replace_atom",
            params=params,
            user=user,
            as_user=as_user,
            server=server,
        ),
    )


# ---------------------------------------------------------------------------
# Terminal aggregator endpoints
# ---------------------------------------------------------------------------


def _terminal_endpoint(method_name: str) -> Any:
    """Build a no-body terminal_* endpoint with a ``limit`` query param.

    The 5 terminal cards have the same shape; this factory keeps the
    router compact without introducing a second router-mounting layer.
    """

    async def _handler(
        agent_id: str,
        limit: int = Query(default=5, ge=1, le=20),
        as_user: int | None = None,
        user: Any = Depends(current_user),
        server: Any = Depends(get_server),
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            call_memory_rpc(
                agent_id=agent_id,
                method=method_name,
                params={"limit": limit},
                user=user,
                as_user=as_user,
                server=server,
            ),
        )

    _handler.__name__ = method_name
    return _handler


router.add_api_route(
    "/agents/{agent_id}/memory/terminal/about_me",
    _terminal_endpoint("terminal_about_me"),
    methods=["GET"],
)
router.add_api_route(
    "/agents/{agent_id}/memory/terminal/current_focus",
    _terminal_endpoint("terminal_current_focus"),
    methods=["GET"],
)
router.add_api_route(
    "/agents/{agent_id}/memory/terminal/things_you_told_me",
    _terminal_endpoint("terminal_things_you_told_me"),
    methods=["GET"],
)
router.add_api_route(
    "/agents/{agent_id}/memory/terminal/recent_stories",
    _terminal_endpoint("terminal_recent_stories"),
    methods=["GET"],
)
router.add_api_route(
    "/agents/{agent_id}/memory/terminal/entities",
    _terminal_endpoint("terminal_entities"),
    methods=["GET"],
)


# ---------------------------------------------------------------------------
# Memory runtime and extraction config (read/write the agent's ``memory`` section)
# ---------------------------------------------------------------------------


def _read_extract_config(row: Any) -> dict[str, Any]:
    """Merge the stored ``memory`` config section over the defaults."""
    try:
        cfg = json.loads(row.config_json or "{}")
    except (TypeError, ValueError):
        cfg = {}
    mem = cfg.get("memory") if isinstance(cfg, dict) else None
    stored = mem if isinstance(mem, dict) else {}
    out = dict(_EXTRACT_DEFAULTS)
    for key in _EXTRACT_DEFAULTS:
        if key in stored:
            out[key] = stored[key]
    return out


def _coerce_seconds(value: Any, *, minimum: float) -> float:
    seconds = float(value)
    if seconds < minimum:
        return minimum
    if seconds > _MAX_SECONDS:
        return _MAX_SECONDS
    return seconds


def _validated_aux_model(value: Any, providers: Any) -> str | None:
    """Normalize an ``aux_model`` patch value: empty / "auto" → None (AUTO)."""
    ref = str(value).strip()
    if not ref or ref.lower() == "auto":
        return None
    if not providers.is_model_ref_usable(ref):
        raise HTTPException(
            status_code=400,
            detail=f"aux_model {ref!r} is not an enabled model on a usable provider",
        )
    return ref


@router.get("/agents/{agent_id}/memory/extract-config")
async def get_extract_config(
    agent_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Return the agent's extraction-trigger configuration (with defaults)."""
    row = require_agent_owner_row(agent_id, user=user, as_user=as_user, server=server)
    return _read_extract_config(row)


@router.put("/agents/{agent_id}/memory/extract-config")
async def put_extract_config(
    agent_id: str,
    body: _ExtractConfigBody = Body(default_factory=_ExtractConfigBody),
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Persist the extraction-trigger config and hot-reload the agent.

    Only owner or admin may write. Unknown/omitted fields keep their stored
    value; seconds are clamped to safe bounds and ``trigger_mode`` validated.
    """
    registry = server.app_runtime.agent_registry
    row = registry.get_row(agent_id)
    if row is None:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
    assert_agent_owner(row, user)

    merged = _read_extract_config(row)
    patch = body.model_dump(exclude_none=True)

    if "memory_enabled" in patch:
        merged["memory_enabled"] = bool(patch["memory_enabled"])
    if "extract_on_session_end" in patch:
        merged["extract_on_session_end"] = bool(patch["extract_on_session_end"])
    if "extract_trigger_mode" in patch:
        mode = str(patch["extract_trigger_mode"])
        if mode not in ("idle", "interval"):
            raise HTTPException(
                status_code=400, detail="extract_trigger_mode must be 'idle' or 'interval'"
            )
        merged["extract_trigger_mode"] = mode
    if "extract_idle_seconds" in patch:
        merged["extract_idle_seconds"] = _coerce_seconds(
            patch["extract_idle_seconds"], minimum=_MIN_IDLE_SECONDS
        )
    if "extract_interval_seconds" in patch:
        merged["extract_interval_seconds"] = _coerce_seconds(
            patch["extract_interval_seconds"], minimum=_MIN_INTERVAL_SECONDS
        )
    if "aux_model" in patch:
        merged["aux_model"] = _validated_aux_model(patch["aux_model"], registry.providers)

    try:
        cfg = json.loads(row.config_json or "{}")
        if not isinstance(cfg, dict):
            cfg = {}
    except (TypeError, ValueError):
        cfg = {}
    existing_mem = cfg.get("memory")
    mem_section = dict(existing_mem) if isinstance(existing_mem, dict) else {}
    mem_section.update(merged)
    cfg["memory"] = mem_section

    await registry.update(agent_id, config_json=json.dumps(cfg))
    return merged


# ---------------------------------------------------------------------------
# Namespace-scoped aggregation (plan T-37)
# ---------------------------------------------------------------------------

ScopeName = Literal["project", "team", "agent"]
ScopeFilter = Literal["project", "team", "agent", "all"]


class MemoryScopeItem(BaseModel):
    """One memory row, tagged with the namespace layer it was read from."""

    id: str
    text: str
    source_layer: str = Field(description="Which layer this row came from: project | team | agent")
    namespace: str = Field(description="The memory namespace the row was read from")
    created_at: str | None = None
    importance: str | None = None
    entity_id: str | None = None
    project_id: str | None = Field(
        default=None, description="Owning project, set for rows from the project layer"
    )


class MemoryScopeGroup(BaseModel):
    """One namespace layer: its namespace, its size, and its rows."""

    source_layer: str
    namespace: str
    total: int
    items: list[MemoryScopeItem]


class MemoryScopesOut(BaseModel):
    agent_id: str
    groups: list[MemoryScopeGroup]


class ProjectMemoryOut(BaseModel):
    project_id: str
    items: list[MemoryScopeItem]
    next_cursor: str | None = None


def _actor(user: User) -> ProjectActor:
    """``User`` already satisfies :class:`ProjectActor`; this keeps mypy honest."""
    return user


def _project_write_target(server: Any, *, user: User, project_id: str) -> Any:
    """Authorise a **project-directed memory write** and return the project row.

    Two separate gates, deliberately not merged (SPEC B38 / §11.3):

    * **write** — ``PROJECT_WRITE`` on the project role table; this is the gate
      that decides. A ``viewer`` is refused here even though they may read the
      project's memory, so "readable" never implies "writable".
    * **read** — ``get_project`` re-checks ``PROJECT_READ`` only to hand back the
      authorised row; it is not the write decision, and it never widens it.

    The returned row is also where the namespace comes from, so a caller who may
    not write the project never learns its ``memory_namespace`` from a write
    request (same discipline as the read routes).
    """
    service = ProjectService(server.services)
    service.assert_project_role(project_id, user=_actor(user), required=PROJECT_WRITE)
    return service.get_project(project_id, user=_actor(user))


def _agent_memory_cfg(server: Any, agent_id: str) -> dict[str, Any]:
    """Return the agent's parsed ``config_json`` (its memory backend lives here)."""
    row = server.services.agent_repo.get(agent_id)
    raw = getattr(row, "config_json", None) if row is not None else None
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _open_recall(server: Any, agent_id: str, team_id: str | None) -> Any:
    """Build the cross-namespace merge layer over the agent's own memory backend."""
    from octop.infra.agents.memory.multi_ns import MemoryScope, MultiNsRecall

    scope = MemoryScope(
        agent_id=agent_id,
        cfg=_agent_memory_cfg(server, agent_id),
        octop_config=server.services.config,
        workspace_dir=resolve_agent_workspace_dir(server, agent_id),
        team_agent_id=team_id,
    )
    return MultiNsRecall(scope)


def _list_layer_atoms(memory: Any, layer: str, *, limit: int, stopwatch: Any) -> list[Any]:
    """Read one layer's atoms under its own deadline.

    Each namespace is treated as one recall source: a namespace that times out
    or fails at the driver contributes no rows and the other layers still
    answer (same discipline as ``multi_ns``'s per-namespace gather).
    """
    from octop_memory.pipeline.recall.timeout import (
        DEFAULT_ATOM_BUDGET_MS,
        TimeoutExceededError,
        with_deadline,
    )
    from octop_memory.storage.driver_errors import DRIVER_ERRORS

    try:
        atoms: list[Any] = with_deadline(
            lambda: memory.list_atoms(limit=limit),
            stage=f"ns:{layer}",
            budget_ms=min(DEFAULT_ATOM_BUDGET_MS, max(1, stopwatch.remaining_ms)),
        )
    except TimeoutExceededError:
        logger.warning("memory scope listing timed out layer=%s", layer)
        return []
    except DRIVER_ERRORS:
        logger.warning("memory scope listing failed layer=%s", layer, exc_info=True)
        return []
    stopwatch.split(f"ns:{layer}")
    return atoms


def _iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _scope_groups(
    recall: Any,
    *,
    project_id: str | None,
    project_namespace: str | None,
    limit: int,
    scopes: Sequence[ScopeName] | None = None,
) -> list[MemoryScopeGroup]:
    """Group each namespace's memories, deduped in project → team → agent order.

    The same fact can live in more than one namespace: the project layer inherits
    the team layer, and both inherit the agent's private layer. Layers are
    therefore merged with the *same* identity rule the recall path uses — memory
    id or normalized text — and the first (highest) layer wins. Concatenating the
    three namespaces would report one memory up to three times (plan R17).
    """
    from octop_memory.pipeline.recall.timeout import DEFAULT_TOTAL_BUDGET_MS, Stopwatch

    from octop.infra.agents.memory.multi_ns import normalize_memory_text

    wanted = set(scopes) if scopes is not None else None
    stopwatch = Stopwatch(total_budget_ms=DEFAULT_TOTAL_BUDGET_MS)
    seen_ids: set[str] = set()
    seen_texts: set[str] = set()
    groups: list[MemoryScopeGroup] = []
    for layer in recall.layers(project_id=project_id):
        if wanted is not None and layer not in wanted:
            continue
        if stopwatch.expired:
            break
        memory = recall.memory_for(
            layer, project_id=project_id, project_namespace=project_namespace
        )
        namespace = str(getattr(memory, "namespace", ""))
        items: list[MemoryScopeItem] = []
        for atom in _list_layer_atoms(memory, layer, limit=limit, stopwatch=stopwatch):
            atom_id = str(getattr(atom, "id", "") or "")
            text = str(getattr(atom, "assertion", "") or "")
            text_key = normalize_memory_text(text)
            if atom_id and atom_id in seen_ids:
                continue
            # A blank snippet carries no identity, so it must not dedupe
            # against another blank one.
            if text_key and text_key in seen_texts:
                continue
            if atom_id:
                seen_ids.add(atom_id)
            if text_key:
                seen_texts.add(text_key)
            items.append(
                MemoryScopeItem(
                    id=atom_id,
                    text=text,
                    source_layer=layer,
                    namespace=namespace,
                    created_at=_iso(getattr(atom, "created_at", None)),
                    importance=getattr(atom, "importance", None),
                    entity_id=getattr(atom, "entity_id", None),
                    project_id=project_id if layer == "project" else None,
                )
            )
        groups.append(
            MemoryScopeGroup(
                source_layer=layer,
                namespace=namespace,
                total=len(items),
                items=items,
            )
        )
    return groups


def _decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        offset = int(cursor)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="cursor must be an integer offset") from exc
    return max(0, offset)


@router.get(
    "/agents/{agent_id}/memory/scopes",
    summary="List memory grouped by namespace scope",
    response_model=MemoryScopesOut,
)
async def list_memory_scopes(
    agent_id: str,
    project_id: str | None = Query(
        default=None,
        description="Project context; the project layer is skipped entirely when omitted",
    ),
    team_id: str | None = Query(
        default=None, description="Team host agent id; omit when the agent belongs to no team"
    ),
    limit: int = Query(default=50, ge=1, le=500),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> MemoryScopesOut:
    """Read the agent's memory grouped by ``agent_{id}`` / ``team_{id}`` / ``project_{id}``.

    The project group appears **only** when ``project_id`` is supplied — the
    project layer is never guessed — and an empty group is an empty state, not an
    error. Rows already contributed by a higher layer are not repeated in a lower
    one (plan R17), so a row shown under ``agent`` is one that is not yet in the
    team or project layer.

    Supplying ``project_id`` requires ``PROJECT_READ`` on that project, exactly
    as on the project-scoped route: reading ``project_{id}`` memory is gated by
    ``project_members`` on **every** path, not only the project one (SPEC §11.3 /
    B38). The namespace is taken from the authorised row, so a non-member never
    learns the project's ``memory_namespace``.
    """
    require_agent_owner_row(agent_id, user=user, as_user=as_user, server=server)
    project_namespace: str | None = None
    if project_id is not None:
        project_namespace = (
            ProjectService(server.services)
            .get_project(project_id, user=_actor(user))
            .memory_namespace
        )
    recall = _open_recall(server, agent_id, team_id)
    try:
        groups = _scope_groups(
            recall,
            project_id=project_id,
            project_namespace=project_namespace,
            limit=limit,
        )
    finally:
        recall.close()
    return MemoryScopesOut(agent_id=agent_id, groups=groups)


@router.get(
    "/projects/{project_id}/memory",
    summary="List a project's memory",
    tags=["projects"],
    response_model=ProjectMemoryOut,
)
async def list_project_memory(
    project_id: str,
    agent_id: str = Query(
        description="Host agent whose memory backend holds the project's namespace"
    ),
    scope: ScopeFilter = Query(default="project"),
    team_id: str | None = Query(default=None, description="Team host agent id, for team scope"),
    cursor: str | None = Query(default=None, description="Opaque offset from a previous page"),
    limit: int = Query(default=50, ge=1, le=500),
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> ProjectMemoryOut:
    """Read ``project_{project_id}`` memory for anyone with ``PROJECT_READ``.

    Membership — not the platform admin flag — guards project data, so a
    non-member is rejected with ``403 PROJECT_FORBIDDEN`` even when it is an
    admin (``ProjectService.assert_project_role``'s documented semantics). A
    project that has no memory yet is an empty state, not an error.

    ``agent_id`` locates the backend only: a project namespace lives inside the
    host agent's workspace, and the run's host is not recorded on the project row
    yet (``team_runs.host_agent_id`` arrives with migration 022), so the caller
    supplies it.
    """
    project = ProjectService(server.services).get_project(project_id, user=_actor(user))

    offset = _decode_cursor(cursor)
    recall = _open_recall(server, agent_id, team_id)
    try:
        groups = _scope_groups(
            recall,
            project_id=project_id,
            project_namespace=project.memory_namespace,
            # One row past the page, so "is there another page" is answerable
            # without reading the whole layer.
            limit=offset + limit + 1,
            scopes=None if scope == "all" else (scope,),
        )
    finally:
        recall.close()

    items = [item for group in groups for item in group.items]
    page = items[offset : offset + limit]
    next_cursor = str(offset + limit) if len(items) > offset + limit else None
    return ProjectMemoryOut(project_id=project_id, items=page, next_cursor=next_cursor)


__all__ = ["router"]
