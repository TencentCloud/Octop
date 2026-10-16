"""Market-quotes plugin must not report an empty quote set as success."""

from __future__ import annotations

import importlib.util
import json
from typing import Any

from octop.infra.agents.plugins.bundled import default_bundled_plugins_root


def _load_market_quotes() -> Any:
    path = default_bundled_plugins_root() / "market-quotes" / "main.py"
    spec = importlib.util.spec_from_file_location("bundled_market_quotes", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeResp:
    def __init__(self, payload: Any, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self) -> Any:
        return self._payload

    @property
    def content(self) -> bytes:
        assert isinstance(self._payload, str)
        return self._payload.encode("gbk", errors="replace")


class _StubClient:
    """Answers each known endpoint with one canned response; touches no network."""

    responses: dict[str, _FakeResp] = {}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.headers = dict(kwargs.get("headers") or {})

    def __enter__(self) -> _StubClient:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def get(self, url: str, **kwargs: Any) -> _FakeResp:
        for needle, resp in type(self).responses.items():
            if needle in url:
                return resp
        raise AssertionError(f"unexpected url {url}")


def _stub(monkeypatch: Any, mod: Any, **responses: _FakeResp) -> None:
    monkeypatch.setattr(_StubClient, "responses", responses, raising=False)
    monkeypatch.setattr(mod.httpx, "Client", _StubClient)


def _card(result: str) -> dict[str, Any]:
    payload = json.loads(result)
    assert payload["octop_ui"]["renderer"] == "market_quotes_card"
    return payload


# Verbatim shape of CoinGecko's reply for a name it does not know: HTTP 200, `{}`.
UNKNOWN_COIN_IDS: dict[str, Any] = {}
# Verbatim shape for one id it does know (values trimmed to the fields the plugin reads).
BITCOIN: dict[str, Any] = {"bitcoin": {"usd": 84273, "cny": 565746, "usd_24h_change": -0.14}}


async def test_unknown_crypto_id_is_reported_as_failure(monkeypatch: Any) -> None:
    mod = _load_market_quotes()
    _stub(monkeypatch, mod, coingecko=_FakeResp(UNKNOWN_COIN_IDS))
    card = _card(await mod.get_crypto(ids="btc"))
    assert card["data"]["rows"] == []
    assert card["data"]["error"]
    assert card["text"].startswith("加密货币查询失败")


async def test_crypto_entry_without_data_is_reported_as_failure(monkeypatch: Any) -> None:
    mod = _load_market_quotes()
    _stub(monkeypatch, mod, coingecko=_FakeResp({"notacoin": None}))
    card = _card(await mod.get_crypto(ids="notacoin"))
    assert card["data"]["rows"] == []
    assert card["data"]["error"]


async def test_known_crypto_id_still_returns_rows(monkeypatch: Any) -> None:
    mod = _load_market_quotes()
    _stub(monkeypatch, mod, coingecko=_FakeResp(BITCOIN))
    card = _card(await mod.get_crypto(ids="bitcoin"))
    assert "error" not in card["data"]
    assert card["data"]["rows"] == [
        {
            "symbol": "bitcoin",
            "price": 84273,
            "price_cny": 565746,
            "pct": -0.14,
            "change": None,
        }
    ]
    assert card["text"].startswith("加密货币：bitcoin $84273")


async def test_forex_without_a_rate_already_fails(monkeypatch: Any) -> None:
    """The convention this file pins for crypto: an empty result is an error."""
    mod = _load_market_quotes()
    _stub(monkeypatch, mod, frankfurter=_FakeResp({"rates": {}, "date": "2026-09-27"}))
    card = _card(await mod.get_forex(base="USD", quote="XZY"))
    assert card["data"]["error"] == "no rate"
    assert card["data"]["rows"] == []


async def test_cn_stock_without_rows_already_fails(monkeypatch: Any) -> None:
    mod = _load_market_quotes()
    _stub(monkeypatch, mod, sinajs=_FakeResp('var hq_str_sh600519="";'))
    card = _card(await mod.get_cn_stock(codes="sh600519"))
    assert card["data"]["error"] == "empty quote"
    assert card["data"]["rows"] == []
