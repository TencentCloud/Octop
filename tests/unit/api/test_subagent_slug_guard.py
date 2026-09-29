"""Slug-shape guard for ``POST /agents/{aid}/subagents/install`` (``SCOPE-2W``).

The install endpoint used to judge the slug with its own predicate (reject only
``/`` and a leading ``.``), which let ``\\`` through -- harmless on POSIX (a
literal filename character) but a path separator on Windows, where
``agents/a\\..\\..\\.octop\\team\\p.md`` folds to a ``.octop/team/**`` write
(``RESEARCH-WRITE-ENTRIES.md`` §5.1). The endpoint now delegates to
:func:`octop.infra.skills.skill_packages.validate_skill_slug`, so there is a
single slug judge in the tree and the reject set is a strict superset of the old
one: ``\\`` and NUL join ``/`` and a leading ``.``, while every previously legal
slug still passes.

The guard runs before the ownership / catalog dependencies, so the rejection case
needs no server; the pass case stubs those dependencies only far enough to show
the slug survived the guard and reached the catalog lookup.

Only locally observable (macOS/POSIX, ``local_shell`` backend): Windows backend
semantics for ``\\`` are **not** exercised here.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException

from octop.api.routers import subagents as subagents_router
from octop.api.routers.subagents import InstallSubagentBody, install_subagent
from octop.infra.errors import ErrorCode, OctopError

LEGAL_SLUG = "code-reviewer"


async def _call_install(slug: str) -> None:
    """Invoke the endpoint with inert dependencies (the guard runs first)."""
    await install_subagent(
        "agent-1",
        InstallSubagentBody(slug=slug),
        request=None,  # type: ignore[arg-type]  # unused before the guard passes
        user=None,
        server=None,
    )


@pytest.mark.parametrize(
    "slug",
    [
        "a\\..\\..\\.octop\\team\\p",  # the §5.1 probe shape (backslash separators)
        "x\\..\\.octop\\team\\LEARNINGS",  # backslash traversal into a protected tree
        "team\x00.md",  # NUL
    ],
)
async def test_slug_with_backslash_or_nul_is_rejected(slug: str) -> None:
    with pytest.raises(HTTPException) as excinfo:
        await _call_install(slug)
    assert excinfo.value.status_code == 400


async def test_legal_slug_passes_the_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Positive control: a legal slug is not caught by the shared judge."""
    monkeypatch.setattr(subagents_router, "require_agent_owner_row", lambda *a, **k: None)
    monkeypatch.setattr(subagents_router, "_require_catalog", lambda server: _EmptyCatalog())

    with pytest.raises(OctopError) as excinfo:
        await _call_install(LEGAL_SLUG)

    # Reaching the catalog lookup at all proves the guard let the slug through.
    assert excinfo.value.code is ErrorCode.NOT_FOUND


class _EmptyCatalog:
    def get(self, slug: str) -> Any:
        return None
