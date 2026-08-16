"""tests/unit/api/test_agent_access.py"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from octop.api.common.agent import (
    agent_is_shared,
    assert_agent_access_row,
    assert_agent_owner,
    user_owns_agent,
)
from octop.infra.errors import ErrorCode, OctopError


def test_owner_may_access() -> None:
    row = SimpleNamespace(user_id=1)
    user = SimpleNamespace(id=1, is_admin=False)
    assert_agent_owner(row, user)


def test_non_owner_forbidden() -> None:
    row = SimpleNamespace(user_id=1)
    user = SimpleNamespace(id=2, is_admin=False)
    with pytest.raises(OctopError) as ei:
        assert_agent_owner(row, user)
    assert ei.value.code is ErrorCode.FORBIDDEN


def test_shared_agent_non_admin_forbidden() -> None:
    row = SimpleNamespace(user_id=None)
    user = SimpleNamespace(id=1, is_admin=False)
    with pytest.raises(OctopError) as ei:
        assert_agent_owner(row, user)
    assert ei.value.code is ErrorCode.FORBIDDEN


def test_shared_agent_admin_allowed() -> None:
    row = SimpleNamespace(user_id=None)
    user = SimpleNamespace(id=1, is_admin=True)
    assert_agent_owner(row, user)


def test_shared_agent_accessible_to_non_owner() -> None:
    row = SimpleNamespace(user_id=1, is_shared=1)
    user = SimpleNamespace(id=2, is_admin=False)
    assert_agent_access_row(row, user)


def test_private_agent_forbidden_to_non_owner() -> None:
    row = SimpleNamespace(user_id=1, is_shared=0)
    user = SimpleNamespace(id=2, is_admin=False)
    with pytest.raises(OctopError) as ei:
        assert_agent_access_row(row, user)
    assert ei.value.code == ErrorCode.FORBIDDEN


def test_shared_non_owner_still_fails_owner_assert() -> None:
    row = SimpleNamespace(user_id=1, is_shared=1)
    user = SimpleNamespace(id=2, is_admin=False)
    with pytest.raises(OctopError):
        assert_agent_owner(row, user)


def test_agent_is_shared_true_when_flag_set() -> None:
    row = SimpleNamespace(is_shared=1)
    assert agent_is_shared(row) is True


def test_agent_is_shared_false_when_missing_or_zero() -> None:
    assert agent_is_shared(SimpleNamespace(is_shared=0)) is False
    assert agent_is_shared(SimpleNamespace()) is False


def test_user_owns_agent_only_for_matching_owner() -> None:
    row = SimpleNamespace(user_id=1)
    owner = SimpleNamespace(id=1, is_admin=False)
    other = SimpleNamespace(id=2, is_admin=False)
    admin = SimpleNamespace(id=99, is_admin=True)
    assert user_owns_agent(row, owner) is True
    assert user_owns_agent(row, other) is False
    assert user_owns_agent(row, admin) is False
