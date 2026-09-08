"""Token quota agent middleware tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from octop.infra.agents.middleware.token_quota import TokenQuotaMiddleware
from octop.infra.errors import ErrorCode, OctopError


def test_token_quota_middleware_rejects_exhausted_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policies = Mock()
    policies.get.return_value = SimpleNamespace(enabled=True, value="10")
    usage = Mock()
    usage.total_tokens_for_user.return_value = 10
    monkeypatch.setattr(
        "octop.infra.agents.middleware.token_quota.get_config",
        lambda: {"configurable": {"user": "7"}},
    )

    middleware = TokenQuotaMiddleware(policy_repo=policies, usage_repo=usage)
    with pytest.raises(OctopError) as exc:
        middleware.before_agent({}, None)

    assert exc.value.code is ErrorCode.TOKEN_QUOTA_EXCEEDED
    assert exc.value.details == {"used": 10, "quota": 10}
    policies.get.assert_called_once_with(7, "token_quota")
    usage.total_tokens_for_user.assert_called_once_with(7)


def test_token_quota_middleware_allows_unlimited_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policies = Mock()
    policies.get.return_value = None
    usage = Mock()
    monkeypatch.setattr(
        "octop.infra.agents.middleware.token_quota.get_config",
        lambda: {"configurable": {"user": 8}},
    )

    middleware = TokenQuotaMiddleware(policy_repo=policies, usage_repo=usage)
    middleware.before_agent({}, None)

    usage.total_tokens_for_user.assert_not_called()


@pytest.mark.asyncio
async def test_token_quota_middleware_async_hook_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policies = Mock()
    policies.get.return_value = SimpleNamespace(enabled=True, value="1")
    usage = Mock()
    usage.total_tokens_for_user.return_value = 1
    monkeypatch.setattr(
        "octop.infra.agents.middleware.token_quota.get_config",
        lambda: {"configurable": {"user": 3}},
    )

    middleware = TokenQuotaMiddleware(policy_repo=policies, usage_repo=usage)
    with pytest.raises(OctopError) as exc:
        await middleware.abefore_agent({}, None)

    assert exc.value.code is ErrorCode.TOKEN_QUOTA_EXCEEDED
