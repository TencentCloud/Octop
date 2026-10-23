"""Unit tests for DeepSeek Search / Fetch config resolution."""

from __future__ import annotations

from octop.infra.websearch.config import (
    API_KEY_ENV,
    DEFAULT_BASE_URL,
    DEFAULT_COUNT,
    DeepSeekSearchConfig,
    clamp_count,
    fetch_endpoint,
    looks_like_deepseek_provider,
    parse_bool,
    resolve_base_url,
    search_endpoint,
)


def test_from_env_requires_a_key() -> None:
    assert DeepSeekSearchConfig.from_env({}) is None
    assert DeepSeekSearchConfig.from_env({"DEEPSEEK_SEARCH_API_KEY": "   "}) is None


def test_from_env_reads_search_key_with_defaults() -> None:
    config = DeepSeekSearchConfig.from_env({API_KEY_ENV: "sk-test"})
    assert config is not None
    assert config.api_key == "sk-test"
    assert config.base_url == DEFAULT_BASE_URL
    assert config.count == DEFAULT_COUNT
    assert config.need_content is False
    assert config.localization == ""


def test_from_env_prefers_explicit_search_only_key() -> None:
    config = DeepSeekSearchConfig.from_env(
        {
            "DEEPSEEK_API_KEY": "sk-models",
            "DEEPSEEK_SEARCH_API_KEY": "sk-search",
        }
    )
    assert config is not None
    assert config.api_key == "sk-search"


def test_from_env_accepts_search_only_key_alias() -> None:
    config = DeepSeekSearchConfig.from_env({"DEEPSEEK_SEARCH_API_KEY": "sk-search"})
    assert config is not None
    assert config.api_key == "sk-search"


def test_from_env_parses_all_options() -> None:
    config = DeepSeekSearchConfig.from_env(
        {
            API_KEY_ENV: "sk-test",
            "DEEPSEEK_SEARCH_BASE_URL": "https://example.test/v1/",
            "DEEPSEEK_SEARCH_COUNT": "25",
            "DEEPSEEK_SEARCH_NEED_CONTENT": "true",
            "DEEPSEEK_SEARCH_LOCALIZATION": " 1.2.3.4 ",
        }
    )
    assert config is not None
    assert config.base_url == "https://example.test/v1"
    assert config.count == 25
    assert config.need_content is True
    assert config.localization == "1.2.3.4"
    assert config.search_url == "https://example.test/v1/tools/search"
    assert config.fetch_url == "https://example.test/v1/tools/fetch"


def test_parse_bool_accepts_env_style_values() -> None:
    assert parse_bool("true") is True
    assert parse_bool("1") is True
    assert parse_bool("YES") is True
    assert parse_bool("on") is True
    assert parse_bool("false") is False
    assert parse_bool("0") is False
    assert parse_bool("") is False
    assert parse_bool("maybe", default=True) is True


def test_clamp_count() -> None:
    assert clamp_count(None) == DEFAULT_COUNT
    assert clamp_count("not-a-number") == DEFAULT_COUNT
    assert clamp_count("0") == 1
    assert clamp_count("99") == 50
    assert clamp_count("7") == 7


def test_endpoint_builders_accept_bare_and_v1_base_urls() -> None:
    assert search_endpoint("https://api.deepseek.com") == (
        "https://api.deepseek.com/v1/tools/search"
    )
    assert search_endpoint("https://api.deepseek.com/v1") == (
        "https://api.deepseek.com/v1/tools/search"
    )
    assert fetch_endpoint("https://api.deepseek.com/") == (
        "https://api.deepseek.com/v1/tools/fetch"
    )
    assert fetch_endpoint("") == f"{DEFAULT_BASE_URL}/v1/tools/fetch"
    assert resolve_base_url("https://proxy.test/v1/") == "https://proxy.test/v1"


def test_looks_like_deepseek_provider() -> None:
    assert looks_like_deepseek_provider("DeepSeek", None) is True
    assert looks_like_deepseek_provider("deepseek-chat", "") is True
    assert looks_like_deepseek_provider("My Gateway", "https://api.deepseek.com/v1") is True
    assert looks_like_deepseek_provider("My Gateway", "https://api.deepseek.com.cn/v1") is False
    assert looks_like_deepseek_provider("OpenAI", "https://api.openai.com/v1") is False
    assert looks_like_deepseek_provider(None, None) is False
