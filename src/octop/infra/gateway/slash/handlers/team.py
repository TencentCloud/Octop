"""``/team`` — the expert-team run command (plan T-19).

A **thin adapter**, not a second implementation of anything:

* every sub-command calls the *same* ``TeamRunService`` object the HTTP surface
  calls (``api/routers/team_runs.py``), obtained from ``SlashCtx.team_run_service``;
* the *same* ownership predicate guards it, supplied as
  ``SlashCtx.authorize_agent_action`` rather than re-implemented here — the
  authority lives in ``api/common/agent.py`` and ``infra/`` may not import
  ``api/`` (``AGENTS.md`` §5), so copying it would create a second, weaker
  permission model;
* the *same* team-agent check the router uses (``is_team_agent``) decides whether
  the target row is a team at all.

When either seam is unwired the command says so **explicitly** instead of
falling back to a weaker check: an unguarded ``/team <goal>`` would create a run
on a team agent the caller has no right to, which is exactly the escalation the
HTTP surface refuses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from octop_harness.slash import SlashCommand, SlashSink

from octop.i18n.domains.slash import tr
from octop.infra.agents.teams.service import is_team_agent
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.slash.ctx import lang_of
from octop.infra.gateway.slash.formatting import markdown_bullets, markdown_kv_block
from octop.infra.gateway.slash.types import GatewayHandler
from octop.infra.users.identity import User
from octop.infra.utils.locale import Locale, normalize_locale

if TYPE_CHECKING:
    from collections.abc import Sequence

    from octop.infra.gateway.slash.ctx import SlashCtx
    from octop.infra.gateway.slash.dispatcher import SlashDispatcher

#: Task ops, exactly the vocabulary the HTTP route accepts (``TaskPatchBody.op``).
TASK_OPS: tuple[str, ...] = ("claim", "start", "report", "complete", "fail", "rework")

#: Sub-commands other than the bare ``/team <goal>`` create form.
SUBCOMMANDS: tuple[str, ...] = (
    "status",
    "task",
    "check",
    "detail",
    "decision",
    "resume",
    "cancel",
    "tier",
    "learn",
    "settle",
)

__all__ = ["SUBCOMMANDS", "TASK_OPS", "cmd_team"]


def _actor(ctx: SlashCtx, lang: Locale) -> User:
    """The caller as a ``ProjectActor`` — the type ``create()``/``decide()`` require.

    A ``SlashCtx`` only knows a bare ``user_id``, while every run transition hands
    ``user`` to ``ProjectService``, which reads ``user.is_admin`` and
    ``user.permissions``. Passing the bare int is what broke ``create()``
    (``'int' object has no attribute 'is_admin'``): the seam and the service each
    held the right half of the contract, and the *shape* at their junction did not
    match.

    The canonical object is ``infra/users/identity.py · User`` — ``is_admin`` is
    **its** derived property (``role == Role.ADMIN``), so resolving the row into
    that class keeps the rule itself in exactly one place. ``role`` and
    ``permissions`` are copied verbatim from the same ``UserRow`` that
    ``UserManager.boot`` feeds its cache from, so the resolved authority is the
    row's, never a locally invented one.

    ``UserManager.get_by_id`` would be the natural accessor, but its cache is built
    from ``SharedServices`` inside the server and is not reachable from a
    ``SlashCtx``; the row is. ``tests/unit/gateway/test_slash_team.py`` binds this
    conversion to ``UserManager``'s, for an admin and a plain user both.
    """
    row = ctx.user_repo.get(ctx.user_id) if ctx.user_repo is not None else None
    if row is None:
        # Same refusal shape as the ownership adapter: an unresolvable subject
        # must not be able to act, and must not be mistaken for a non-admin.
        raise OctopError(ErrorCode.FORBIDDEN, tr("team.user_inactive", lang))
    return User(
        id=row.id,
        username=row.username,
        role=str(row.role),
        display_name=row.display_name,
        locale=normalize_locale(row.locale),
        permissions=list(row.permissions or []),
    )


def _unknown(lang: Locale, *, detail: dict[str, Any] | None = None) -> OctopError:
    """Refuse with the plan's boundary code and the allowed values attached."""
    return OctopError(
        ErrorCode.TEAM_COMMAND_UNKNOWN,
        tr("team.unknown", lang),
        details=detail or {},
    )


def _require_service(ctx: SlashCtx, lang: Locale) -> Any:
    service = ctx.team_run_service
    if service is None:
        raise _unknown(lang, detail={"reason": "team_run_service_unwired"})
    return service


def _authorize_team(ctx: SlashCtx, lang: Locale, team_agent_id: str) -> None:
    """The router's own gate, via the injected predicate (never a local copy)."""
    if ctx.authorize_agent_action is None:
        raise _unknown(lang, detail={"reason": "authorizer_unwired"})
    row = ctx.agent_manager.get_row(team_agent_id) if ctx.agent_manager is not None else None
    if row is None or not is_team_agent(row):
        raise OctopError(ErrorCode.TEAM_NOT_FOUND, tr("team.not_found", lang, run=team_agent_id))
    ctx.authorize_agent_action(row, ctx.user_id)


def _authorize_run(ctx: SlashCtx, lang: Locale, service: Any, run_id: str) -> Any:
    """``require_run`` + the team-row ownership gate, in the router's order."""
    run = service.require_run(run_id)
    _authorize_team(ctx, lang, run.team_agent_id)
    return run


def _run_id(args: Sequence[str], lang: Locale) -> str:
    if not args:
        raise _unknown(lang, detail={"allowed": list(SUBCOMMANDS)})
    return args[0]


async def _create(ctx: SlashCtx, service: Any, goal: str, sink: SlashSink, lang: Locale) -> None:
    team_agent_id = ctx.agent_id
    _authorize_team(ctx, lang, team_agent_id)
    run = service.create(team_agent_id=team_agent_id, user=_actor(ctx, lang), goal=goal)
    await sink.text(
        markdown_kv_block(
            tr("team.created", lang, run=run.run_id),
            [
                (tr("team.field.phase", lang), str(run.phase)),
                (tr("team.field.tier", lang), str(run.tier)),
                (tr("team.field.mode", lang), str(run.mode)),
            ],
        )
    )


async def _status(
    ctx: SlashCtx, service: Any, args: Sequence[str], sink: SlashSink, lang: Locale
) -> None:
    run = _authorize_run(ctx, lang, service, _run_id(args, lang))
    await sink.text(
        markdown_kv_block(
            tr("team.status_title", lang, run=run.run_id),
            [
                (tr("team.field.status", lang), str(run.status)),
                (tr("team.field.phase", lang), str(run.phase)),
                (tr("team.field.tier", lang), str(run.tier)),
                (tr("team.field.goal", lang), run.goal[:80]),
                (tr("team.field.stranded", lang), str(len(service.stranded(run.run_id)))),
            ],
        )
    )


async def _task(
    ctx: SlashCtx, service: Any, args: Sequence[str], sink: SlashSink, lang: Locale
) -> None:
    if len(args) < 3:
        raise _unknown(lang, detail={"allowed": list(TASK_OPS)})
    run_id, task_id, op = args[0], args[1], args[2].lower()
    if op not in TASK_OPS:
        raise _unknown(lang, detail={"allowed": list(TASK_OPS)})
    _authorize_run(ctx, lang, service, run_id)
    role = args[3] if len(args) > 3 else None
    method = getattr(service, op)
    method(run_id, task_id, role=role, user=_actor(ctx, lang))
    await sink.text(tr("team.task_done", lang, task=task_id, op=op))


async def _check(
    ctx: SlashCtx, service: Any, args: Sequence[str], sink: SlashSink, lang: Locale
) -> None:
    run = _authorize_run(ctx, lang, service, _run_id(args, lang))
    report = service.check(run.run_id)
    violations = list(getattr(report, "violations", ()) or ())
    if not violations:
        await sink.text(tr("team.check_clean", lang, run=run.run_id))
        return
    bullets = [str(getattr(v, "detail", v)) for v in violations[:15]]
    await sink.text(markdown_bullets(tr("team.check_title", lang, run=run.run_id), bullets))


async def _detail(
    ctx: SlashCtx, service: Any, args: Sequence[str], sink: SlashSink, lang: Locale
) -> None:
    run = _authorize_run(ctx, lang, service, _run_id(args, lang))
    snapshot = service.snapshot(run)
    phases = snapshot.get("phases") or []
    bullets = [f"`{p.get('phase')}` — {p.get('status')}" for p in phases[:15]]
    await sink.text(markdown_bullets(tr("team.detail_title", lang, run=run.run_id), bullets))


async def _decision(
    ctx: SlashCtx, service: Any, args: Sequence[str], sink: SlashSink, lang: Locale
) -> None:
    if len(args) < 2:
        raise _unknown(lang, detail={"allowed": ["<run_id> <choice> [note]"]})
    run = _authorize_run(ctx, lang, service, args[0])
    choice, note = args[1], " ".join(args[2:])
    # The decision id comes from the run, never from the caller: the service
    # refuses anything that is not the pending one (TEAM_DECISION_NOT_PENDING).
    pending = service.snapshot(run).get("pending_decision") or {}
    decision_id = str(pending.get("decision_id") or "")
    if not decision_id:
        await sink.text(tr("team.decision_none", lang, run=run.run_id))
        return
    result = service.decide(
        run.run_id, decision_id=decision_id, choice=choice, note=note, user=_actor(ctx, lang)
    )
    await sink.text(
        tr(
            "team.decision_done",
            lang,
            run=run.run_id,
            choice=choice,
            status=result.get("status", ""),
        )
    )


async def _resume(
    ctx: SlashCtx, service: Any, args: Sequence[str], sink: SlashSink, lang: Locale
) -> None:
    run = _authorize_run(ctx, lang, service, _run_id(args, lang))
    updated = service.resume(run.run_id, user=_actor(ctx, lang))
    await sink.text(tr("team.resume_done", lang, run=updated.run_id, status=updated.status))


async def _cancel(
    ctx: SlashCtx, service: Any, args: Sequence[str], sink: SlashSink, lang: Locale
) -> None:
    run = _authorize_run(ctx, lang, service, _run_id(args, lang))
    updated = service.cancel(run.run_id, user=_actor(ctx, lang))
    await sink.text(tr("team.cancel_done", lang, run=updated.run_id))


async def _tier(
    ctx: SlashCtx, service: Any, args: Sequence[str], sink: SlashSink, lang: Locale
) -> None:
    from octop.infra.agents.teams.pipeline import TIER_SPEC

    run = _authorize_run(ctx, lang, service, _run_id(args, lang))
    bullets = [f"`{name}` — roleCap {spec.role_cap}" for name, spec in sorted(TIER_SPEC.items())]
    await sink.text(
        markdown_bullets(tr("team.tier_title", lang, run=run.run_id, tier=run.tier), bullets)
    )


async def _learn(
    ctx: SlashCtx, service: Any, args: Sequence[str], sink: SlashSink, lang: Locale
) -> None:
    run = _authorize_run(ctx, lang, service, _run_id(args, lang))
    names = list(service.present_artifacts(run))
    if not names:
        await sink.text(tr("team.learn_none", lang, run=run.run_id))
        return
    await sink.text(markdown_bullets(tr("team.learn_title", lang, run=run.run_id), names[:20]))


async def _settle(
    ctx: SlashCtx, service: Any, args: Sequence[str], sink: SlashSink, lang: Locale
) -> None:
    """``/team settle <run_id> [task_id …]`` — the write the HTTP ``:settle`` does.

    The judgement is **not** repeated here (``I5``): the service settles the tuple its
    own ``stranded()`` produced, so what ``/team status`` counts and what this command
    writes cannot drift apart. An empty result is an answer, not a refusal — the reply
    says there was nothing to settle and nothing was written (``SPEC §5.2-2``).

    Extra arguments are task ids to narrow the set; no reason syntax is invented on the
    slash face, because the service's default (``reason=""``) is already the full set.
    """
    run = _authorize_run(ctx, lang, service, _run_id(args, lang))
    settled = service.settle(run.run_id, task_ids=list(args[1:]), user=_actor(ctx, lang))
    if not settled:
        await sink.text(tr("team.settle_none", lang, run=run.run_id))
        return
    await sink.text(
        markdown_bullets(
            tr("team.settle_title", lang, run=run.run_id, count=len(settled)),
            [f"`{task_id}`" for task_id in settled],
        )
    )


_DISPATCH: dict[str, Any] = {
    "status": _status,
    "settle": _settle,
    "task": _task,
    "check": _check,
    "detail": _detail,
    "decision": _decision,
    "resume": _resume,
    "cancel": _cancel,
    "tier": _tier,
    "learn": _learn,
}


async def cmd_team(d: SlashDispatcher, cmd: SlashCommand, ctx: SlashCtx, sink: SlashSink) -> None:
    """``/team <goal>`` creates a run; ``/team <sub-command> …`` drives one."""
    lang = lang_of(ctx)
    service = _require_service(ctx, lang)
    raw = (cmd.args or "").strip()
    if not raw:
        await sink.text(tr("team.usage", lang))
        return

    head, _, rest = raw.partition(" ")
    handler = _DISPATCH.get(head.lower())
    if handler is None:
        # No sub-command word: the whole argument is the goal (plan T-19).
        if head.lower() in SUBCOMMANDS:
            raise _unknown(lang, detail={"allowed": list(SUBCOMMANDS)})
        await _create(ctx, service, raw, sink, lang)
        return
    await handler(ctx, service, rest.split(), sink, lang)


GATEWAY_HANDLER: GatewayHandler = cmd_team
