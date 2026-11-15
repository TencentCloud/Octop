"""Catalog completeness for built-in web-search providers."""

from __future__ import annotations

from octop.infra.utils.search_providers import (
    SEARCH_PROVIDER_IDS,
    SEARCH_PROVIDERS,
    get_search_provider,
    personal_search_providers,
)


def test_catalog_covers_every_builtin_provider() -> None:
    assert SEARCH_PROVIDER_IDS == (
        "tavily",
        "brave",
        "deepseek",
        "google",
        "kimi",
        "yuanbao",
        "you",
        "searchfree",
    )


def test_google_requires_both_env_vars() -> None:
    google = get_search_provider("google")
    assert google is not None
    assert google.env_vars == ("GOOGLE_API_KEY", "GOOGLE_CSE_ID")


def test_deepseek_has_a_global_endpoint_env() -> None:
    deepseek = get_search_provider("deepseek")
    assert deepseek is not None
    assert deepseek.endpoint_env == "DEEPSEEK_SEARCH_ENDPOINT"


def test_you_accepts_optional_key_and_searchfree_does_not() -> None:
    you = get_search_provider("you")
    searchfree = get_search_provider("searchfree")
    assert you is not None and you.env_vars == ()
    assert you.optional_env_vars == ("YDC_API_KEY",)
    assert you.personal_key is True
    assert searchfree is not None and searchfree.personal_key is False


def test_personal_catalog_excludes_searchfree() -> None:
    ids = {spec.id for spec in personal_search_providers()}
    assert "searchfree" not in ids
    assert ids == {spec.id for spec in SEARCH_PROVIDERS if spec.id != "searchfree"}


def test_unknown_provider_is_none() -> None:
    assert get_search_provider("nope") is None
