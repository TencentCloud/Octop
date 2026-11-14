"""Per-user provider key resolution (bring-your-own-key) and turn plumbing."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from octop.infra.agents.providers.user_keys import resolve_api_key_override
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.process.harness_request import build_harness_request


def _row(
    name: str = "gw",
    api_key: str | None = "sk-global",
    extra_json: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(name=name, api_key=api_key, extra_json=extra_json)


class _ProviderRepo:
    def __init__(self, row: SimpleNamespace | None) -> None:
        self._row = row

    def get_by_name(self, name: str) -> SimpleNamespace | None:
        if self._row is not None and self._row.name == name:
            return self._row
        return None


class _KeyRepo:
    def __init__(self, keys: dict[tuple[int, str], str] | None = None) -> None:
        self._keys = dict(keys or {})

    def get_key(self, user_id: int, provider_name: str) -> str | None:
        return self._keys.get((user_id, provider_name))


def _resolve(
    *,
    user_id: int = 7,
    model_ref: str | None = "gw/gpt",
    row: SimpleNamespace | None = None,
    keys: dict[tuple[int, str], str] | None = None,
) -> str | None:
    return resolve_api_key_override(
        user_id=user_id,
        model_ref=model_ref,
        provider_repo=_ProviderRepo(row if row is not None else _row()),
        user_provider_key_repo=_KeyRepo(keys),
    )


def test_user_key_overrides_global_key() -> None:
    assert _resolve(keys={(7, "gw"): "sk-personal"}) == "sk-personal"


def test_missing_key_falls_back_to_global() -> None:
    assert _resolve() is None


def test_keyless_provider_without_key_raises() -> None:
    row = _row(api_key="")
    with pytest.raises(OctopError) as excinfo:
        _resolve(row=row)
    assert excinfo.value.code == ErrorCode.PROVIDER_KEY_REQUIRED
    envelope = excinfo.value.to_envelope(locale="zh")
    assert envelope["error"]["code"] == "PROVIDER_KEY_REQUIRED"
    assert "个人 API 密钥" in str(envelope["error"]["message"])


def test_keyless_provider_with_key_returns_key() -> None:
    row = _row(api_key=None)
    assert _resolve(row=row, keys={(7, "gw"): "sk-personal"}) == "sk-personal"


def test_explicitly_keyless_provider_returns_none() -> None:
    row = _row(api_key=None, extra_json='{"keyless": true}')
    assert _resolve(row=row) is None


def test_system_callers_never_raise() -> None:
    assert _resolve(user_id=0, row=_row(api_key="")) is None


def test_unknown_provider_and_no_ref_return_none() -> None:
    assert _resolve(row=None) is None
    assert _resolve(model_ref=None) is None


def test_build_harness_request_carries_api_key_override() -> None:
    req: dict[str, Any] = build_harness_request(
        thread_id="t1",
        user_id=7,
        source="web/x",
        content="hi",
        api_key_override="sk-personal",
    )
    assert req["configurable"]["api_key_override"] == "sk-personal"
    req2 = build_harness_request(
        thread_id="t1",
        user_id=7,
        source="web/x",
        messages=[{"role": "user", "content": "hi"}],
        api_key_override="sk-personal",
    )
    assert req2["configurable"]["api_key_override"] == "sk-personal"
    req3 = build_harness_request(thread_id="t1", user_id=7, source="web/x", content="hi")
    assert "api_key_override" not in req3.get("configurable", {})
