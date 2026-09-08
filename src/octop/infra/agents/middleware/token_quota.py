"""Reject agent turns when the acting user has exhausted their token quota."""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langgraph.config import get_config

from octop.infra.users.resource_policy import assert_token_quota_available


def configurable_user_id() -> int | None:
    try:
        configurable = dict(get_config().get("configurable") or {})
    except RuntimeError:
        return None
    raw = configurable.get("user")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return None


class TokenQuotaMiddleware(AgentMiddleware[Any, Any]):
    """Check the acting user's lifetime token total before an agent turn."""

    def __init__(self, *, policy_repo: Any, usage_repo: Any) -> None:
        super().__init__()
        self._policies = policy_repo
        self._usage = usage_repo

    def _enforce(self) -> None:
        user_id = configurable_user_id()
        if user_id is not None:
            assert_token_quota_available(self._policies, self._usage, user_id)

    def before_agent(self, state: Any, runtime: Any) -> None:
        del state, runtime
        self._enforce()

    async def abefore_agent(self, state: Any, runtime: Any) -> None:
        del state, runtime
        self._enforce()


__all__ = ["TokenQuotaMiddleware", "configurable_user_id"]
