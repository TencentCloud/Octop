"""SKILL_MARKET_ORIGIN resolution for the skill market HTTP client."""

from __future__ import annotations

import pytest

from octop.infra.skills.skillhub_common import skill_market_origin
from octop.infra.skills.skillhub_market import SkillHubMarketError, _resolve_host


def test_unset_origin_is_the_public_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SKILL_MARKET_ORIGIN", raising=False)
    assert skill_market_origin() == "https://api.skillhub.cn"


def test_origin_keeps_scheme_host_and_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILL_MARKET_ORIGIN", "http://market.internal:9000/ignored?q=1")
    assert skill_market_origin() == "http://market.internal:9000"
    assert _resolve_host(None) == "http://market.internal:9000"


def test_bare_host_defaults_to_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILL_MARKET_ORIGIN", "market.internal")
    assert skill_market_origin() == "https://market.internal"


def test_explicit_host_argument_wins_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILL_MARKET_ORIGIN", "http://from-env.example")
    assert skill_market_origin("http://from-arg.example/path") == "http://from-arg.example"


def test_invalid_origin_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILL_MARKET_ORIGIN", "ftp://files.example")
    with pytest.raises(ValueError, match="ftp://files.example"):
        skill_market_origin()
    with pytest.raises(SkillHubMarketError, match="Invalid SkillHub API host"):
        _resolve_host(None)
