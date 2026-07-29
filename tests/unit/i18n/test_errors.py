"""tests/unit/i18n/test_errors.py"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from octop.i18n import error_message
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.locale import resolve_request_locale


def test_every_error_code_has_i18n_entry():
    for code in ErrorCode:
        assert error_message(code.value, "en")
        assert error_message(code.value, "zh")


def test_error_message_zh():
    assert "名称" in error_message("AGENT_NAME_TAKEN", "zh")


def test_octop_error_localized_factory():
    err = OctopError.localized(ErrorCode.FORBIDDEN, "zh")
    assert err.code is ErrorCode.FORBIDDEN
    assert err.message == "没有权限。"


def test_octop_error_to_envelope_with_locale():
    err = OctopError(ErrorCode.AGENT_NAME_TAKEN, "agent name 'x' already in use")
    envelope = err.to_envelope(locale="zh")
    assert envelope["error"]["code"] == "AGENT_NAME_TAKEN"
    assert envelope["error"]["message"] == "该名称已被使用，请换一个名称。"


def test_resolve_request_locale_from_accept_language():
    class _Headers:
        def get(self, key: str) -> str | None:
            if key.lower() == "accept-language":
                return "zh-CN,en;q=0.9"
            return None

    class _Req:
        headers = _Headers()

    assert resolve_request_locale(_Req()) == "zh"


def test_dashboard_api_errors_match_backend():
    repo = Path(__file__).resolve().parents[3]
    dash_en = json.loads((repo / "dashboard/src/locales/en.json").read_text(encoding="utf-8"))
    backend_en = json.loads((repo / "src/octop/i18n/en.json").read_text(encoding="utf-8"))
    dash_codes = set(dash_en["apiErrors"].keys())
    backend_codes = set(backend_en["errors"].keys())
    assert dash_codes == backend_codes == {c.value for c in ErrorCode}


# i18next uses ``{{name}}``; a lone ``{name}`` is left uninterpolated in the UI.
_DASHBOARD_SINGLE_BRACE = re.compile(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})")


def test_dashboard_api_errors_use_i18next_placeholders():
    repo = Path(__file__).resolve().parents[3]
    for locale in ("en", "zh"):
        data = json.loads(
            (repo / f"dashboard/src/locales/{locale}.json").read_text(encoding="utf-8")
        )
        for code, msg in data["apiErrors"].items():
            found = _DASHBOARD_SINGLE_BRACE.findall(msg)
            assert not found, (
                f"{locale} apiErrors.{code} uses Python-style {{{', '.join(found)}}} — "
                "dashboard i18next needs {{name}} double braces"
            )


def test_login_locked_interpolates_minutes():
    assert "15" in error_message("LOGIN_LOCKED", "zh", minutes=15)
    assert "minutes" not in error_message("LOGIN_LOCKED", "zh", minutes=15).lower()
    assert "{minutes}" not in error_message("LOGIN_LOCKED", "en", minutes=15)


def test_localized_message_falls_back_when_key_missing(monkeypatch: pytest.MonkeyPatch):
    err = OctopError(ErrorCode.AUTH_FAILED, "custom detail")
    monkeypatch.setattr(
        "octop.infra.errors.i18n_error_message",
        lambda *_a, **_k: (_ for _ in ()).throw(KeyError("errors.X")),
    )
    assert err.localized_message("zh") == "custom detail"
