"""The wechat-ops publisher must not reuse another account's cached token.

WeChat access tokens are scoped to a single official account. The publisher
keeps one cache file for every account, so the record has to carry the AppID it
was issued for; otherwise switching WECHAT_APP_ID keeps publishing into the
previous account while still reporting success.
"""

from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from octop.infra.agents.experts.catalog import default_library_root

_SCRIPT = (
    default_library_root()
    / "wechat-ops"
    / "skills"
    / "publisher-multi-platform"
    / "scripts"
    / "wechat_publish.py"
)


def _load_wechat_publish() -> ModuleType:
    spec = importlib.util.spec_from_file_location("wechat_publish_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


def _install_fake_httpx(
    module: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_get(url: str, params: dict[str, Any] | None = None, timeout: int = 0) -> _FakeResponse:
        calls.append({"url": url, "params": params or {}})
        return _FakeResponse(
            {"access_token": f"fresh-{params['appid']}", "expires_in": 7200}  # type: ignore[index]
        )

    monkeypatch.setattr(module.httpx, "get", fake_get)
    return calls


def _write_cache(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_cached_token_is_not_reused_for_another_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_wechat_publish()
    cache = tmp_path / "token.json"
    _write_cache(
        cache,
        {"app_id": "wx-old-account", "access_token": "stale", "expires_at": time.time() + 3600},
    )
    monkeypatch.setattr(module, "TOKEN_CACHE_FILE", str(cache))
    monkeypatch.setenv("WECHAT_APP_ID", "wx-new-account")
    monkeypatch.setenv("WECHAT_APP_SECRET", "secret")
    calls = _install_fake_httpx(module, monkeypatch)

    assert module.get_wechat_access_token() == "fresh-wx-new-account"
    assert [call["params"]["appid"] for call in calls] == ["wx-new-account"]


def test_cached_token_without_an_app_id_is_refetched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_wechat_publish()
    cache = tmp_path / "token.json"
    _write_cache(cache, {"access_token": "stale", "expires_at": time.time() + 3600})
    monkeypatch.setattr(module, "TOKEN_CACHE_FILE", str(cache))
    monkeypatch.setenv("WECHAT_APP_ID", "wx-current")
    monkeypatch.setenv("WECHAT_APP_SECRET", "secret")
    calls = _install_fake_httpx(module, monkeypatch)

    assert module.get_wechat_access_token() == "fresh-wx-current"
    assert len(calls) == 1


def test_cached_token_is_reused_for_the_same_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_wechat_publish()
    cache = tmp_path / "token.json"
    _write_cache(
        cache,
        {"app_id": "wx-current", "access_token": "cached", "expires_at": time.time() + 3600},
    )
    monkeypatch.setattr(module, "TOKEN_CACHE_FILE", str(cache))
    monkeypatch.setenv("WECHAT_APP_ID", "wx-current")
    monkeypatch.setenv("WECHAT_APP_SECRET", "secret")
    calls = _install_fake_httpx(module, monkeypatch)

    assert module.get_wechat_access_token() == "cached"
    assert calls == []


def test_fetched_token_is_cached_with_its_app_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_wechat_publish()
    cache = tmp_path / "token.json"
    monkeypatch.setattr(module, "TOKEN_CACHE_FILE", str(cache))
    monkeypatch.setenv("WECHAT_APP_ID", "wx-current")
    monkeypatch.setenv("WECHAT_APP_SECRET", "secret")
    _install_fake_httpx(module, monkeypatch)

    assert module.get_wechat_access_token() == "fresh-wx-current"

    written = json.loads(cache.read_text(encoding="utf-8"))
    assert written["app_id"] == "wx-current"
    assert written["access_token"] == "fresh-wx-current"
