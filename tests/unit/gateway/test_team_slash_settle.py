"""``/team settle`` — the slash face of A2 (``TASKS.json`` T7).

Three contracts are pinned here, and nothing else is re-tested:

1. **The usage line *is* the sub-command set, word for word.** ``catalog.usage``,
   the ``slash.team.usage`` copy in en/zh, and ``SUBCOMMANDS`` are compared against
   each other, so a sub-command that exists but is not advertised (or the reverse)
   cannot pass.
2. **``settle`` is a thin adapter.** It calls ``TeamRunService.settle`` and prints
   what the service returned (count + ids). ``_FakeService`` below exposes *only*
   the public seams, so a handler that reached for a repo/DB handle to "do the work
   itself" fails with ``AttributeError`` instead of passing quietly — the judgement
   (``stranded_tasks`` / ``settle_tasks``, ``pipeline.py``) is never duplicated here,
   and this file asserts no threshold, epoch rule, or candidate set of its own.
3. **An empty result is an answer, not a refusal.** ``settled: []`` prints the
   "nothing to settle" copy — and nothing is written (``SPEC §5.2-2`` / ``B15``):
   the handler touches no write seam, and the one call it makes is the service's own
   ``settle``, which returns ``[]`` before any write.

Localisation: the zh and en copies each get their own test rather than a loop, so a
broken side is visible on its own (``tests/unit/i18n/test_teams_i18n.py`` convention).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from octop_harness.slash import SlashCommand

import octop.infra.gateway.slash.handlers.team as team_handler
from octop.i18n import tr
from octop.infra.gateway.slash import BufferSink, build_default_dispatcher
from octop.infra.gateway.slash.catalog import spec_for
from octop.infra.gateway.slash.ctx import SlashCtx
from octop.infra.gateway.slash.handlers.team import SUBCOMMANDS, cmd_team

#: The only ``TeamRunService`` members the slash face may touch (``TASKS.json`` T7).
SEAMS: tuple[str, ...] = ("require_run", "settle", "stranded")


def _usage() -> str:
    """The one legal usage line, derived from the tuple the dispatcher actually uses."""
    return "/team <goal> | " + "|".join(SUBCOMMANDS)


class _FakeService:
    """A service-shaped object exposing the seams **and nothing else**."""

    def __init__(self, *, settled: list[str] | None = None, stranded: int = 0) -> None:
        self.settled = list(settled or [])
        self.stranded_count = stranded
        self.calls: list[tuple[str, str]] = []
        self.settle_calls: list[dict[str, Any]] = []

    def require_run(self, run_id: str) -> Any:
        self.calls.append(("require_run", run_id))
        return SimpleNamespace(
            run_id=run_id,
            team_agent_id="team-1",
            status="running",
            phase="build",
            tier="standard",
            goal="ship the settle face",
        )

    def settle(
        self, run_id: str, *, task_ids: Any = (), reason: str = "", user: Any = None
    ) -> list[str]:
        self.calls.append(("settle", run_id))
        self.settle_calls.append({"task_ids": list(task_ids), "reason": reason, "user": user})
        return list(self.settled)

    def stranded(self, run_id: str) -> tuple[Any, ...]:
        self.calls.append(("stranded", run_id))
        return tuple(SimpleNamespace(id=f"S{index}") for index in range(self.stranded_count))

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(
            f"/team reached for service.{name!r}, but only {SEAMS} are seams: the judgement "
            "and the writes belong to TeamRunService, never to the handler"
        )


def _ctx(service: Any, *, locale: str = "zh") -> SlashCtx:
    manager = MagicMock()
    manager.get_row.return_value = SimpleNamespace(agent_id="team-1", user_id=7, kind="team")
    user_repo = MagicMock()
    user_repo.get.return_value = SimpleNamespace(
        id=7,
        username="u7",
        role="user",
        display_name=None,
        locale=locale,
        permissions=["projects"],
    )
    return SlashCtx(
        agent_id="team-1",
        user_id=7,
        channel_type="feishu",
        session_key="team-1:feishu:u7:dm",
        thread_registry=MagicMock(),
        agent_manager=manager,
        user_repo=user_repo,
        locale=locale,
        team_run_service=service,
        authorize_agent_action=lambda *_args: None,
    )


def _allow_team(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the row-taxonomy gate: *is this a team row* is another file's contract."""
    monkeypatch.setattr(team_handler, "is_team_agent", lambda _row: True)


async def _run(ctx: SlashCtx, args: str) -> str:
    sink = BufferSink()
    await cmd_team(build_default_dispatcher(), SlashCommand(name="team", args=args), ctx, sink)
    return "\n".join(sink.lines)


# ---------------------------------------------------------------------------
# 1. usage == the real sub-command set (catalog + both locales)
# ---------------------------------------------------------------------------


def test_catalog_usage_is_the_subcommand_set_word_for_word() -> None:
    spec = spec_for("team")
    assert spec is not None
    assert spec.usage == _usage()
    listed = tuple(part.strip() for part in spec.usage.split("|")[1:])
    assert listed == SUBCOMMANDS
    assert listed[-1] == "settle"
    assert "settle" in SUBCOMMANDS


def test_slash_team_usage_copy_is_english_in_the_en_locale() -> None:
    en = tr("slash.team.usage", "en")
    assert en == f"Usage: {_usage()}"
    assert tuple(part.strip() for part in en.split("|")[1:]) == SUBCOMMANDS


def test_slash_team_usage_copy_is_chinese_in_the_zh_locale() -> None:
    zh = tr("slash.team.usage", "zh")
    # The zh head is localised ("用法：/team <目标> | "); the sub-command list is not.
    assert zh.startswith("用法：/team <目标> | ")
    assert tuple(part.strip() for part in zh.split("|")[1:]) == SUBCOMMANDS


# ---------------------------------------------------------------------------
# 2. settle delegates to the service and echoes what it returned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_settle_delegates_to_the_service_and_echoes_count_and_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_team(monkeypatch)
    service = _FakeService(settled=["T3", "T4"])
    out = await _run(_ctx(service), "settle RUN1")

    # Only the two seams — in particular *no* ``stranded`` call: the handler does not
    # re-derive the candidate set, it prints the service's answer (``I5``).
    assert [name for name, _ in service.calls] == ["require_run", "settle"]
    assert service.settle_calls[0]["task_ids"] == []
    assert service.settle_calls[0]["reason"] == ""
    assert service.settle_calls[0]["user"].is_admin is False
    assert tr("slash.team.settle_title", "zh", run="RUN1", count=2) in out
    assert "T3" in out and "T4" in out


@pytest.mark.asyncio
async def test_settle_passes_extra_arguments_as_task_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_team(monkeypatch)
    service = _FakeService(settled=["T9"])
    out = await _run(_ctx(service), "settle RUN1 T9 T10")

    assert [name for name, _ in service.calls] == ["require_run", "settle"]
    assert service.settle_calls[0]["task_ids"] == ["T9", "T10"]
    assert "T9" in out


# ---------------------------------------------------------------------------
# 3. the empty set: an answer, not a refusal — and no write
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_settle_of_an_empty_set_answers_in_zh_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_team(monkeypatch)
    service = _FakeService(settled=[])
    out = await _run(_ctx(service), "settle RUN1")

    assert tr("slash.team.settle_none", "zh", run="RUN1") in out
    assert "无可清算" in out
    # Negative assertion: nothing was written. The strict fake raises on any non-seam
    # attribute (so a ``service._tasks.update(...)`` shortcut is a failure, not a pass),
    # and the only call made is the service's own ``settle`` — which returns ``[]``
    # before touching a row (``run_service.settle``, ``SPEC §5.2-2``).
    assert [name for name, _ in service.calls] == ["require_run", "settle"]
    assert service.settle_calls[0]["task_ids"] == []


@pytest.mark.asyncio
async def test_settle_of_an_empty_set_answers_in_en(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_team(monkeypatch)
    service = _FakeService(settled=[])
    out = await _run(_ctx(service, locale="en"), "settle RUN1")

    assert tr("slash.team.settle_none", "en", run="RUN1") in out
    assert "Nothing to settle" in out


# ---------------------------------------------------------------------------
# 4. status reports the stranded count the service reports
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_shows_the_stranded_count_the_service_reports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_team(monkeypatch)
    service = _FakeService(stranded=2)
    out = await _run(_ctx(service), "status RUN1")

    assert ("stranded", "RUN1") in service.calls
    assert tr("slash.team.field.stranded", "zh") in out
    assert "2" in out
