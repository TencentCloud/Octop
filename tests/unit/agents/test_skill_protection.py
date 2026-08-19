"""Unit tests for published-expert skill-detail protection guards."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from octop.infra.agents.experts.skill_protection import (
    assert_skill_details_visible,
    assert_workspace_path_allowed,
    protected_slugs_from_config,
    skill_details_protected,
    snapshot_protected_skill_slugs,
)
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.identity import Role, User


def _user(uid: int, *, admin: bool = False) -> User:
    return User(
        id=uid,
        username=f"user{uid}",
        role=Role.ADMIN if admin else Role.USER,
        display_name=None,
    )


class _Repo:
    def __init__(self, rows: dict[str, Any]) -> None:
        self._rows = rows

    def get(self, expert_id: str) -> Any:
        return self._rows.get(expert_id)


def _services(created_by: str | None = "7") -> Any:
    row = None if created_by is None else SimpleNamespace(id="e1", created_by=created_by)
    return SimpleNamespace(published_expert_repo=_Repo({"e1": row}))


RESTRICTED: dict[str, Any] = {
    "skill_details_restricted": True,
    "protected_skills": ["secret-flow"],
    "published_expert_id": "e1",
}


def test_unrestricted_config_has_no_protected_slugs() -> None:
    assert protected_slugs_from_config({}) == frozenset()
    assert protected_slugs_from_config({"protected_skills": ["a"]}) == frozenset()


def test_skill_details_protected_respects_membership_and_exempt_users() -> None:
    peer = _user(9)
    publisher = _user(7)
    admin = _user(8, admin=True)

    assert skill_details_protected(RESTRICTED, user=peer, services=_services(), slug="secret-flow")
    assert not skill_details_protected(
        RESTRICTED, user=publisher, services=_services(), slug="secret-flow"
    )
    assert not skill_details_protected(
        RESTRICTED, user=admin, services=_services(), slug="secret-flow"
    )
    # Non-protected skills stay fully usable / editable.
    assert not skill_details_protected(
        RESTRICTED, user=peer, services=_services(), slug="my-own-skill"
    )
    # Once the expert is unpublished the stamped restriction persists for
    # everyone - the config is the source of truth, not the live row.
    assert skill_details_protected(
        RESTRICTED, user=publisher, services=_services(created_by=None), slug="secret-flow"
    )


def test_assert_skill_details_visible_raises_for_protected_slug() -> None:
    with pytest.raises(OctopError) as exc:
        assert_skill_details_visible(
            RESTRICTED, user=_user(9), services=_services(), slug="secret-flow"
        )
    assert exc.value.code is ErrorCode.SKILL_DETAILS_PROTECTED
    assert exc.value.status == 403

    # No-op for unrestricted agents / non-protected slugs.
    assert_skill_details_visible({}, user=_user(9), services=_services(), slug="x")
    assert_skill_details_visible(RESTRICTED, user=_user(9), services=_services(), slug="other")


@pytest.mark.parametrize(
    ("rel_path", "blocked"),
    [
        ("skills/secret-flow/SKILL.md", True),
        ("skills/secret-flow", True),
        ("skills", True),  # whole-tree mutation (delete / move / archive)
        ("skills/my-own-skill/SKILL.md", False),
        ("SOUL.md", False),
        ("daily/2026-01-01.md", False),
        ("agents/reviewer.md", False),
    ],
)
def test_workspace_path_guard(rel_path: str, blocked: bool) -> None:
    peer = _user(9)
    if blocked:
        with pytest.raises(OctopError) as exc:
            assert_workspace_path_allowed(
                RESTRICTED, user=peer, services=_services(), rel_path=rel_path
            )
        assert exc.value.code is ErrorCode.SKILL_DETAILS_PROTECTED
    else:
        assert_workspace_path_allowed(
            RESTRICTED, user=peer, services=_services(), rel_path=rel_path
        )


def test_workspace_path_guard_allows_publisher_and_ignores_unrestricted() -> None:
    assert_workspace_path_allowed(
        RESTRICTED,
        user=_user(7),
        services=_services(),
        rel_path="skills/secret-flow/SKILL.md",
    )
    assert_workspace_path_allowed(
        {}, user=_user(9), services=_services(), rel_path="skills/secret-flow/SKILL.md"
    )


def test_snapshot_protected_skill_slugs_lists_only_skill_dirs(tmp_path: Path) -> None:
    (tmp_path / "skills" / "alpha").mkdir(parents=True)
    (tmp_path / "skills" / "alpha" / "SKILL.md").write_text("x", encoding="utf-8")
    (tmp_path / "skills" / "beta").mkdir(parents=True)  # no SKILL.md
    (tmp_path / "skills" / "loose.md").write_text("x", encoding="utf-8")

    assert snapshot_protected_skill_slugs(tmp_path) == ["alpha"]
    assert snapshot_protected_skill_slugs(tmp_path / "missing") == []
