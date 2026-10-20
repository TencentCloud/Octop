"""Memory CLI: `candidate` subcommand group for L1 candidates.

Subcommands:
- ``memory candidate extract`` — run extractor against a session's raw events.
  Hidden ``--dev-llm`` flag exists for local prompt validation (D25).
- ``memory candidate list`` — list candidates with status / session filters.
- ``memory candidate show`` — full detail of a single candidate.
- ``memory candidate promote`` — run the 5-check promotion worker (M2.5).
- ``memory candidate review`` — interactive review for needs_review / conflict.

The promote subcommand is the user-facing entry point for the promotion
worker. Its hidden ``--dev-llm`` flag wires ``ModelEscalationHook``
for local entity-disambiguation testing; production host adapters inject
their configured LLM client.
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, get_args

import click

from octop_memory.adapters.cli.config import get_memory
from octop_memory.domain.alias import normalize_alias
from octop_memory.pipeline.extractor import CandidateExtractor, extract_session
from octop_memory.pipeline.promotion.checks import build_atom_from_candidate
from octop_memory.pipeline.promotion.fallback import (
    DEFAULT_REJECTION_THRESHOLD,
    DEFAULT_STALE_DAYS,
    run_fallback_pass,
)
from octop_memory.pipeline.promotion.llm_hook import ModelEscalationHook
from octop_memory.ports.llm import LLMClient, NoopLLMClient, OpenAICompatClient
from octop_memory.types import (
    Alias,
    Candidate,
    CandidateStatus,
    CandidateType,
    Entity,
    JournalEntry,
)

_CANDIDATE_STATUSES = list(get_args(CandidateStatus))
_CANDIDATE_TYPES = list(get_args(CandidateType))


def _candidate_to_dict(c: Candidate) -> dict[str, Any]:
    return {
        "id": c.id,
        "raw_event_ids": c.raw_event_ids,
        "candidate_type": c.candidate_type,
        "status": c.status,
        "title": c.title,
        "assertion": c.assertion,
        "verbatim_quote": c.verbatim_quote,
        "quote_event_id": c.quote_event_id,
        "subject_name": c.subject_name,
        "subject_entity_type": c.subject_entity_type,
        "target_entity_id": c.target_entity_id,
        "confidence": c.confidence,
        "importance": c.importance,
        "recommended_action": c.recommended_action,
        "promotion_reason": c.promotion_reason,
        "extractor_version": c.extractor_version,
        "created_at": c.created_at.isoformat(),
        "decided_at": c.decided_at.isoformat() if c.decided_at else None,
        "decided_by": c.decided_by,
        "session_id": c.session_id,
    }


# Ollama exposes an OpenAI-compatible API at /v1, so both --dev-llm
# providers ride the production OpenAICompatClient.
_OLLAMA_OPENAI_BASE_URL = "http://localhost:11434/v1"
_DEV_LLM_KEY_ENV = "OCTOP_MEMORY_DEV_LLM_KEY"


def _parse_dev_llm(spec: str | None, *, timeout_seconds: float = 600.0) -> LLMClient:
    """Parse ``--dev-llm=<provider>:<...>`` into an LLMClient.

    Supported provider specs:

    - ``ollama:<model>`` — local Ollama (OpenAI-compatible ``/v1``
      endpoint), e.g. ``ollama:qwen3:4b``
    - ``remote:<base_url>:<model>`` — OpenAI-compatible remote endpoint,
      e.g. ``remote:https://api.openai.com/v1:gpt-4o-mini``. The API key
      MUST come from the ``OCTOP_MEMORY_DEV_LLM_KEY`` environment
      variable (never the CLI to keep keys out of shell history).

    Returns ``NoopLLMClient`` when ``spec`` is ``None`` so extract can
    still run end-to-end without a host LLM (degraded path: produces
    ``failure_reason`` in the result).
    """
    if spec is None:
        return NoopLLMClient()
    if ":" not in spec:
        raise click.BadParameter(f"--dev-llm must be 'ollama:<model>' or 'remote:<base_url>:<model>', got {spec!r}")
    provider, rest = spec.split(":", 1)

    if provider == "ollama":
        # Local model cold-start can be slow; keep the generous timeout.
        return OpenAICompatClient(
            base_url=_OLLAMA_OPENAI_BASE_URL,
            model=rest,
            timeout_seconds=timeout_seconds,
        )

    if provider == "remote":
        # rest is "<base_url>:<model>" — split from the right because the
        # base_url itself contains colons (e.g. https://...).
        if ":" not in rest:
            raise click.BadParameter(
                f"--dev-llm=remote requires '<base_url>:<model>' (got rest={rest!r}). "
                f"Example: remote:https://api.openai.com/v1:gpt-4o-mini"
            )
        base_url, model = rest.rsplit(":", 1)
        # Remote endpoints typically respond in seconds; clamp the very
        # generous local-model default.
        remote_timeout = min(timeout_seconds, 120.0)
        return OpenAICompatClient(
            base_url=base_url,
            model=model,
            api_key_env=_DEV_LLM_KEY_ENV,
            timeout_seconds=remote_timeout,
        )

    raise click.BadParameter(
        f"--dev-llm provider must be 'ollama' or 'remote', got {provider!r}. "
        f"Example: 'ollama:qwen3:4b' or 'remote:https://api.openai.com/v1:gpt-4o-mini'"
    )


@click.group(name="candidate")
def candidate_group() -> None:
    """Inspect / extract L1 candidate memories."""


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------


@candidate_group.command(name="extract")
@click.option(
    "--session",
    "session_id",
    default=None,
    help="Session id to extract from. If omitted, extract from the most recent session.",
)
@click.option(
    "--since",
    default=None,
    help="ISO 8601 datetime or duration like '24h' / '7d'. Extracts each session that started after this point.",
)
@click.option(
    "--dev-llm",
    "dev_llm_spec",
    default=None,
    hidden=True,
    help="(dev-only) LLM backend spec, e.g. 'ollama:qwen3:4b'. Production paths must use a host LLM client (D25).",
)
@click.option(
    "--max-candidates",
    default=20,
    show_default=True,
    type=int,
    help="HARD cap on candidates per batch. Above this the extractor emits __cap_warning__.",
)
@click.option(
    "--no-persist",
    is_flag=True,
    default=False,
    help="Do not save candidates to the backend; just print them. Useful for prompt tuning.",
)
@click.pass_context
def extract_cmd(
    ctx: click.Context,
    session_id: str | None,
    since: str | None,
    dev_llm_spec: str | None,
    max_candidates: int,
    no_persist: bool,
) -> None:
    """Extract candidate memories from raw events of a session.

    By default this command runs against a single session. Pass ``--since``
    to iterate over every session whose first raw event falls after the
    given timestamp / duration.

    LLM resolution (D25):

    - In production a host adapter (OpenClaw/Hermes) injects a real LLM
      client at startup; this CLI does not see it.
    - For dev validation, pass ``--dev-llm=ollama:qwen3:4b`` (hidden flag).
    - With no LLM available the extractor returns a graceful failure_reason
      instead of raising — useful to verify the wiring without a model.
    """
    memory = get_memory(ctx)
    llm = _parse_dev_llm(dev_llm_spec)
    extractor = CandidateExtractor(llm=llm, max_candidates=max_candidates)

    sessions: list[str] = _resolve_target_sessions(memory, session_id=session_id, since=since)
    if not sessions:
        click.echo("No sessions matched. Use --session=<id> or --since=<duration>.", err=True)
        sys.exit(1)

    output_json: bool = ctx.obj.get("output_json", False)
    overall: list[dict[str, Any]] = []

    for sid in sessions:
        result = extract_session(
            memory=memory,
            extractor=extractor,
            session_id=sid,
            persist=not no_persist,
        )
        summary = {
            "session_id": sid,
            "candidates": [_candidate_to_dict(c) for c in result.candidates],
            "warnings": result.warnings,
            "cap_warning": result.cap_warning,
            "failure_reason": result.failure_reason,
            "llm_calls": result.llm_calls,
            "persisted": (not no_persist) and bool(result.candidates),
        }
        overall.append(summary)
        if not output_json:
            _print_session_summary(summary)

    if output_json:
        click.echo(json.dumps(overall, ensure_ascii=False, indent=2))


def _resolve_target_sessions(
    memory: Any,
    *,
    session_id: str | None,
    since: str | None,
) -> list[str]:
    if session_id:
        return [session_id]

    if since:
        cutoff = _parse_since(since)
        events = memory.list_raw(after=cutoff, limit=10_000)
    else:
        # Latest session only — pull recent raw events and pick the newest session.
        events = memory.list_raw(limit=200)

    seen: list[str] = []
    seen_set: set[str] = set()
    for ev in events:
        sid = ev.session_id
        if sid and sid not in seen_set:
            seen_set.add(sid)
            seen.append(sid)
    if since is None and len(seen) > 1:
        return [seen[0]]
    return seen


def _parse_since(spec: str) -> datetime:
    """Accept either an ISO datetime or a short duration like '24h' / '7d' / '30m'."""
    spec = spec.strip()
    if spec[-1:].isalpha():
        unit = spec[-1].lower()
        try:
            value = int(spec[:-1])
        except ValueError as e:
            raise click.BadParameter(f"--since must be ISO datetime or like '24h': {spec!r}") from e
        delta_map = {"m": timedelta(minutes=value), "h": timedelta(hours=value), "d": timedelta(days=value)}
        if unit not in delta_map:
            raise click.BadParameter(f"--since: unsupported unit {unit!r} (use m / h / d)")
        return datetime.now().astimezone() - delta_map[unit]
    try:
        return datetime.fromisoformat(spec)
    except ValueError as e:
        raise click.BadParameter(f"--since: invalid ISO 8601 datetime: {spec!r}") from e


def _print_session_summary(summary: dict[str, Any]) -> None:
    sid = summary["session_id"]
    cands: list[dict[str, Any]] = summary["candidates"]
    click.echo(f"=== session={sid} ===")
    if summary["failure_reason"]:
        click.echo(f"  FAILED: {summary['failure_reason']}", err=True)
        return
    click.echo(f"  candidates: {len(cands)}  (llm_calls={summary['llm_calls']}, persisted={summary['persisted']})")
    if summary["cap_warning"]:
        click.echo(f"  cap_warning: {summary['cap_warning']}")
    for w in summary["warnings"]:
        click.echo(f"  ! {w}")
    for c in cands:
        click.echo(f"  - [{c['importance']}/{c['confidence']}] {c['candidate_type']}: {c['title']!s}")
        click.echo(f"      assertion: {c['assertion'][:100]}")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@candidate_group.command(name="list")
@click.option("--status", type=click.Choice(_CANDIDATE_STATUSES), default=None)
@click.option("--session", "session_id", default=None)
@click.option("--target-entity", "target_entity_id", default=None)
@click.option("--limit", default=50, show_default=True, type=int)
@click.pass_context
def list_cmd(
    ctx: click.Context,
    status: str | None,
    session_id: str | None,
    target_entity_id: str | None,
    limit: int,
) -> None:
    """List candidates with optional filters."""
    memory = get_memory(ctx)
    cands = memory.list_candidates(
        status=status,  # type: ignore[arg-type]
        session_id=session_id,
        target_entity_id=target_entity_id,
        limit=limit,
    )

    if ctx.obj.get("output_json"):
        click.echo(json.dumps([_candidate_to_dict(c) for c in cands], ensure_ascii=False, indent=2))
        return

    if not cands:
        click.echo("No candidates found.")
        return
    for c in cands:
        click.echo(f"{c.id[:8]}  [{c.status:14s}] {c.importance}/{c.confidence}  {c.candidate_type:18s}  {c.title}")


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


@candidate_group.command(name="show")
@click.argument("candidate_id")
@click.pass_context
def show_cmd(ctx: click.Context, candidate_id: str) -> None:
    """Show full details of a candidate by id."""
    memory = get_memory(ctx)
    c = memory.get_candidate(candidate_id)
    if c is None:
        click.echo(f"Candidate {candidate_id} not found.", err=True)
        sys.exit(1)

    if ctx.obj.get("output_json"):
        click.echo(json.dumps(_candidate_to_dict(c), ensure_ascii=False, indent=2))
        return

    click.echo(f"id            : {c.id}")
    click.echo(f"status        : {c.status}")
    click.echo(f"type          : {c.candidate_type}")
    click.echo(f"title         : {c.title}")
    click.echo(f"importance    : {c.importance}")
    click.echo(f"confidence    : {c.confidence}")
    click.echo(f"recommended   : {c.recommended_action}")
    click.echo(f"subject       : {c.subject_name} ({c.subject_entity_type})")
    click.echo(f"target entity : {c.target_entity_id or '-'}")
    click.echo(f"session       : {c.session_id or '-'}")
    click.echo(f"created_at    : {c.created_at.isoformat()}")
    click.echo(f"decided_at    : {c.decided_at.isoformat() if c.decided_at else '-'}")
    click.echo(f"decided_by    : {c.decided_by or '-'}")
    click.echo(f"raw_event_ids : {c.raw_event_ids}")
    click.echo(f"quote_event   : {c.quote_event_id}")
    click.echo(f"extractor_ver : {c.extractor_version}")
    click.echo("")
    click.echo("assertion:")
    click.echo(f"  {c.assertion}")
    click.echo("verbatim_quote:")
    click.echo(f"  {c.verbatim_quote}")
    click.echo("promotion_reason:")
    click.echo(f"  {c.promotion_reason}")


# ---------------------------------------------------------------------------
# promote
# ---------------------------------------------------------------------------


@candidate_group.command(name="promote")
@click.option(
    "--candidate-id",
    "candidate_ids",
    multiple=True,
    help="Promote specific candidate id(s). Repeatable. If omitted, promotes all pending.",
)
@click.option(
    "--limit",
    default=50,
    show_default=True,
    type=int,
    help="When promoting all pending, cap the batch size.",
)
@click.option(
    "--dev-llm",
    "dev_llm_spec",
    default=None,
    hidden=True,
    help="(dev-only) wire LLMEscalationHook with this LLM. "
    "Format same as `candidate extract`: 'ollama:<model>' / 'remote:<base>:<model>'.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Preview decisions without writing atoms / journal / status updates.",
)
@click.pass_context
def promote_cmd(
    ctx: click.Context,
    candidate_ids: tuple[str, ...],
    limit: int,
    dev_llm_spec: str | None,
    dry_run: bool,
) -> None:
    """Run the 5-check promotion worker.

    Default mode: pick up every ``pending`` candidate (up to ``--limit``)
    and run the rule pipeline against each. Pass ``--candidate-id=<id>``
    one or more times to target specific rows (useful for retrying a
    single ``needs_review`` after fixing data).

    Decisions land synchronously — when this command returns, the DB
    already reflects every atom / entity / alias / journal write.

    M2.5b: pass ``--dev-llm=...`` to enable LLM-based entity
    disambiguation when alias / canonical_name lookup misses (1 LLM
    call per candidate budget). Production deployments use
    ``ModelEscalationHook`` injected by the host adapter.
    """
    memory = get_memory(ctx)

    if dry_run:
        click.echo(
            "--dry-run is not yet implemented; use a disposable database "
            "or export a backup before preview experiments.",
            err=True,
        )
        sys.exit(2)

    llm_hook: object | None = None
    if dev_llm_spec is not None:
        llm = _parse_dev_llm(dev_llm_spec)
        llm_hook = ModelEscalationHook(llm)

    if candidate_ids:
        cands: list[Candidate] = []
        for cid in candidate_ids:
            c = memory.get_candidate(cid)
            if c is None:
                click.echo(f"Candidate {cid!r} not found.", err=True)
                sys.exit(1)
            cands.append(c)
        result = memory.promote_candidates(cands, llm_hook=llm_hook)
    else:
        result = memory.promote_candidates(limit=limit, llm_hook=llm_hook)

    if ctx.obj.get("output_json"):
        click.echo(json.dumps(_promotion_result_to_dict(result), ensure_ascii=False, indent=2))
        return

    click.echo(
        f"promoted={result.promoted}  merged={result.merged}  "
        f"conflicts={result.conflicts}  needs_review={result.needs_review}  "
        f"dropped={result.dropped}  llm_calls={result.llm_calls}"
    )
    for d in result.decisions:
        head = f"  [{d.outcome.kind:13s}] {d.candidate_id[:8]}"
        if d.atom is not None:
            head += f"  → atom={d.atom.id[:8]}"
        if d.outcome.entity_id:
            head += f"  entity={d.outcome.entity_id[:8]}"
        click.echo(head)
        click.echo(f"      reason: {d.outcome.reason}")


def _promotion_result_to_dict(result: Any) -> dict[str, Any]:
    return {
        "promoted": result.promoted,
        "merged": result.merged,
        "conflicts": result.conflicts,
        "needs_review": result.needs_review,
        "dropped": result.dropped,
        "llm_calls": result.llm_calls,
        "decisions": [
            {
                "candidate_id": d.candidate_id,
                "outcome": d.outcome.kind,
                "reason": d.outcome.reason,
                "entity_id": d.outcome.entity_id,
                "matched_atom_id": d.outcome.matched_atom_id,
                "atom_id": d.atom.id if d.atom is not None else None,
            }
            for d in result.decisions
        ],
    }


# ---------------------------------------------------------------------------
# review (interactive)
# ---------------------------------------------------------------------------


_REVIEW_PROMPT = """\
[a] approve     mark as promoted (creates atom + entity if missing)
[r] reject      mark as rejected (no atom; journaled as user reject)
[m] merge       attach to existing atom by id
[s] skip        leave the candidate as-is, move to next
[q] quit        leave the queue (remaining candidates stay unchanged)
"""


@candidate_group.command(name="review")
@click.option(
    "--status",
    type=click.Choice(["needs_review", "conflict", "pending"]),
    default="needs_review",
    show_default=True,
    help="Which queue to review. 'pending' is rare — usually you promote first.",
)
@click.option("--limit", default=20, show_default=True, type=int)
@click.option("--non-interactive", is_flag=True, default=False, help="Print queue and exit (no prompts).")
@click.pass_context
def review_cmd(
    ctx: click.Context,
    status: str,
    limit: int,
    non_interactive: bool,
) -> None:
    """Walk the review queue and let the user resolve each candidate.

    Approve / reject / merge / skip / quit. Every decision lands one
    journal entry with ``actor="user"``.

    Approve performs the same DB writes as the auto promotion path:
    creates / reuses an entity, builds an AtomCard, bumps atom_count.
    """
    memory = get_memory(ctx)
    queue: list[Candidate] = memory.list_candidates(status=status, limit=limit)  # type: ignore[arg-type]

    if not queue:
        click.echo(f"No candidates in {status!r} queue.")
        return

    click.echo(f"=== review queue: {len(queue)} candidate(s) in status={status!r} ===\n")

    if non_interactive:
        for c in queue:
            click.echo(f"  - {c.id[:8]}  {c.candidate_type:12s}  {c.title}")
            click.echo(f"      assertion: {c.assertion[:120]}")
        return

    counters = {"approve": 0, "reject": 0, "merge": 0, "skip": 0}

    for idx, cand in enumerate(queue, 1):
        click.echo(f"--- [{idx}/{len(queue)}] candidate {cand.id[:8]} ---")
        click.echo(f"  status        : {cand.status}")
        click.echo(f"  type          : {cand.candidate_type}")
        click.echo(f"  importance    : {cand.importance}  confidence: {cand.confidence}")
        click.echo(f"  subject       : {cand.subject_name} ({cand.subject_entity_type})")
        click.echo(f"  title         : {cand.title}")
        click.echo(f"  assertion     : {cand.assertion}")
        click.echo(f"  verbatim_quote: {cand.verbatim_quote}")
        if cand.target_entity_id:
            ent = memory.get_entity(cand.target_entity_id)
            if ent is not None:
                click.echo(f"  target_entity : {ent.id[:8]} {ent.entity_type}:{ent.canonical_name}")
                hot = memory.list_atoms(entity_id=ent.id, limit=3)
                for h in hot:
                    click.echo(f"     · existing: [{h.importance}] {h.assertion[:80]}")
        click.echo("")
        click.echo(_REVIEW_PROMPT)

        choice = click.prompt(
            "choice",
            type=click.Choice(list("armsq")),
            default="s",
            show_default=True,
        )
        if choice == "q":
            click.echo("Quit. Remaining candidates left unchanged.")
            break

        now = datetime.now(UTC)
        if choice == "a":
            entity_id = cand.target_entity_id
            if not entity_id:
                normalized = normalize_alias(cand.subject_name)
                hit = memory.find_entity_by_alias(normalized) if normalized else None
                if hit is None and cand.subject_name.strip():
                    hit = memory.find_entity_by_name(
                        cand.subject_name,
                        entity_type=cand.subject_entity_type,
                    )
                if hit is not None:
                    entity_id = hit.id
                else:
                    entity_id = str(uuid.uuid4())
                    memory.add_entity(
                        Entity(
                            id=entity_id,
                            entity_type=cand.subject_entity_type,
                            canonical_name=cand.subject_name,
                            aliases=[],
                            atom_count=0,
                            created_at=now,
                        )
                    )
                if normalized:
                    memory.add_alias(
                        Alias(
                            alias=normalized,
                            entity_id=entity_id,
                            entity_type=cand.subject_entity_type,
                            created_by="user",
                            created_at=now,
                        )
                    )

            atom = build_atom_from_candidate(
                cand,
                atom_id=str(uuid.uuid4()),
                entity_id=entity_id,
                now=now,
            )
            memory.add_atom(atom)
            memory.bump_entity_atom_count(entity_id, delta=1, last_promoted_at=now)
            memory.update_candidate_status(
                cand.id,
                status="promoted",
                decided_by="user",
                decided_at=now,
                target_entity_id=entity_id,
                promotion_reason="user-approved via review CLI",
            )
            memory.append_journal(
                JournalEntry(
                    id=str(uuid.uuid4()),
                    timestamp=now,
                    action="promote",
                    actor="user",
                    target_entity_id=entity_id,
                    target_atom_id=atom.id,
                    target_candidate_id=cand.id,
                    note="user-approved via review CLI",
                )
            )
            counters["approve"] += 1
            click.echo(f"  → approved (atom={atom.id[:8]}, entity={entity_id[:8]})\n")

        elif choice == "r":
            note = click.prompt(
                "reason (optional, leave empty for default)",
                default="",
                show_default=False,
            )
            memory.update_candidate_status(
                cand.id,
                status="rejected",
                decided_by="user",
                decided_at=now,
                promotion_reason=note or "user-rejected via review CLI",
            )
            memory.append_journal(
                JournalEntry(
                    id=str(uuid.uuid4()),
                    timestamp=now,
                    action="reject",
                    actor="user",
                    target_candidate_id=cand.id,
                    note=note or "user-rejected via review CLI",
                )
            )
            counters["reject"] += 1
            click.echo("  → rejected\n")

        elif choice == "m":
            target_atom_id = click.prompt("target atom id (full UUID)").strip()
            existing = memory.get_atom(target_atom_id)
            if existing is None:
                click.echo(f"  ! atom {target_atom_id} not found; skipping\n", err=True)
                counters["skip"] += 1
                continue
            memory.update_candidate_status(
                cand.id,
                status="promoted",
                decided_by="user",
                decided_at=now,
                target_entity_id=existing.entity_id,
                promotion_reason=f"user-merged into atom {target_atom_id}",
            )
            memory.append_journal(
                JournalEntry(
                    id=str(uuid.uuid4()),
                    timestamp=now,
                    action="merge",
                    actor="user",
                    target_entity_id=existing.entity_id,
                    target_atom_id=existing.id,
                    target_candidate_id=cand.id,
                    note=f"user-merged into atom {existing.id}",
                )
            )
            counters["merge"] += 1
            click.echo(f"  → merged into {existing.id[:8]} (entity={existing.entity_id[:8]})\n")

        else:  # 's'
            counters["skip"] += 1
            click.echo("  → skipped\n")

    click.echo(
        f"\n=== summary ===\napprove={counters['approve']}  reject={counters['reject']}  "
        f"merge={counters['merge']}  skip={counters['skip']}"
    )


# ---------------------------------------------------------------------------
# fallback (M2.8)
# ---------------------------------------------------------------------------


@candidate_group.command(name="fallback")
@click.option(
    "--stale-days",
    default=DEFAULT_STALE_DAYS,
    show_default=True,
    type=int,
    help="needs_review older than this is auto-promoted as confidence=low.",
)
@click.option(
    "--rejection-threshold",
    default=DEFAULT_REJECTION_THRESHOLD,
    show_default=True,
    type=int,
    help="Pending candidates whose assertion was rejected this many times re-escalate to needs_review.",
)
@click.option(
    "--limit",
    default=200,
    show_default=True,
    type=int,
    help="Cap candidates scanned per pass.",
)
@click.pass_context
def fallback_cmd(
    ctx: click.Context,
    stale_days: int,
    rejection_threshold: int,
    limit: int,
) -> None:
    """Run M2.8 fallback rules: 7-day auto-promote + repeated-rejection escalate.

    Idempotent and synchronous. Recommend running on a daily cron once
    OpenClaw integration is live.
    """
    memory = get_memory(ctx)
    result = run_fallback_pass(
        memory,
        stale_days=stale_days,
        rejection_threshold=rejection_threshold,
        limit=limit,
    )

    if ctx.obj.get("output_json"):
        click.echo(
            json.dumps(
                {
                    "stale_promoted": result.stale_promoted,
                    "re_escalated": result.re_escalated,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    click.echo(f"stale_promoted={len(result.stale_promoted)}  re_escalated={len(result.re_escalated)}")
    if result.stale_promoted:
        click.echo("  promoted (>= 7d in needs_review):")
        for cid in result.stale_promoted:
            click.echo(f"    - {cid[:8]}")
    if result.re_escalated:
        click.echo("  re-escalated to needs_review (repeated rejection):")
        for cid in result.re_escalated:
            click.echo(f"    - {cid[:8]}")
