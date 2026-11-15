"""Per-turn resolution of personal search credentials."""

from __future__ import annotations

from typing import Any

from octop.infra.agents.providers.search_keys import resolve_search_tool_env


class _FakeRepo:
    def __init__(self, stored: dict[int, dict[str, str]]) -> None:
        self._stored = stored
        self.calls = 0

    def get_all_env(self, user_id: int) -> dict[str, str]:
        self.calls += 1
        return dict(self._stored.get(user_id, {}))


def test_returns_the_users_env_from_one_scan() -> None:
    repo = _FakeRepo(
        {
            7: {
                "DEEPSEEK_API_KEY": "sk-deepseek",
                "GOOGLE_API_KEY": "g-key",
                "GOOGLE_CSE_ID": "g-cse",
            }
        }
    )
    env = resolve_search_tool_env(user_id=7, search_key_repo=repo)
    assert env == {
        "DEEPSEEK_API_KEY": "sk-deepseek",
        "GOOGLE_API_KEY": "g-key",
        "GOOGLE_CSE_ID": "g-cse",
    }
    assert repo.calls == 1


def test_no_stored_keys_returns_empty_for_global_fallback() -> None:
    assert resolve_search_tool_env(user_id=7, search_key_repo=_FakeRepo({})) == {}


def test_keys_are_per_user() -> None:
    repo = _FakeRepo({8: {"DEEPSEEK_API_KEY": "sk-eight"}})
    assert resolve_search_tool_env(user_id=7, search_key_repo=repo) == {}
    assert resolve_search_tool_env(user_id=8, search_key_repo=repo) == {
        "DEEPSEEK_API_KEY": "sk-eight"
    }


def test_non_user_callers_never_get_overrides() -> None:
    class _ExplodingRepo:
        def get_all_env(self, *_args: Any) -> dict[str, str]:  # pragma: no cover
            raise AssertionError("must not read personal keys for non-user callers")

    assert resolve_search_tool_env(user_id=0, search_key_repo=_ExplodingRepo()) == {}
    assert resolve_search_tool_env(user_id=-1, search_key_repo=_ExplodingRepo()) == {}
