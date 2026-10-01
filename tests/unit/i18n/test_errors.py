"""tests/unit/i18n/test_errors.py"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from octop.i18n import error_message
from octop.infra.errors import _DEFAULT_STATUS, ErrorCode, OctopError
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


# ``docs/api.md`` "## Error envelope" is the human-facing list of codes a client can be
# served. ``OctopError`` resolves its status from ``_DEFAULT_STATUS`` unless a raise site
# overrides it, so the table's HTTP column is the code's default status.
_API_DOC_ROW = re.compile(r"^\|\s*`([A-Z][A-Z0-9_]*)`\s*\|\s*(\d{3})\s*\|", re.M)

# Codes the table documents ahead of the enum because an open issue asks for them.
# Empty by default: a new row must name a code ``ErrorCode`` already has.
_API_DOC_PENDING_CODES = frozenset({"CRON_PROMPT_INVALID"})


def test_api_doc_error_table_lists_real_codes_with_real_statuses():
    repo = Path(__file__).resolve().parents[3]
    doc = (repo / "docs/api.md").read_text(encoding="utf-8")
    section = doc[doc.index("## Error envelope") :]
    rows = [(m.group(1), int(m.group(2))) for m in _API_DOC_ROW.finditer(section)]
    assert rows, "no table rows parsed — the '## Error envelope' table moved or changed shape"

    known = {c.value for c in ErrorCode}
    phantom = [
        code for code, _status in rows if code not in known and code not in _API_DOC_PENDING_CODES
    ]
    assert not phantom, (
        f"docs/api.md lists codes that octop.infra.errors.ErrorCode has not: {phantom}"
    )

    stale = [
        (code, status, _DEFAULT_STATUS[ErrorCode(code)])
        for code, status in rows
        if code in known and _DEFAULT_STATUS[ErrorCode(code)] != status
    ]
    assert not stale, (
        "docs/api.md HTTP column disagrees with _DEFAULT_STATUS "
        f"(code, documented, default): {stale}"
    )


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


def test_knowledge_doc_too_large_interpolates_max_mb():
    assert "100" in error_message("KNOWLEDGE_DOC_TOO_LARGE", "zh", max_mb=100)
    assert "{max_mb}" not in error_message("KNOWLEDGE_DOC_TOO_LARGE", "en", max_mb=100)


def test_localized_message_falls_back_when_key_missing(monkeypatch: pytest.MonkeyPatch):
    err = OctopError(ErrorCode.AUTH_FAILED, "custom detail")
    monkeypatch.setattr(
        "octop.infra.errors.i18n_error_message",
        lambda *_a, **_k: (_ for _ in ()).throw(KeyError("errors.X")),
    )
    assert err.localized_message("zh") == "custom detail"


def test_config_file_corrupt_interpolates_path_and_detail():
    kwargs = {"path": "~/.octop/config.json", "detail": "line 3, column 1"}
    assert "~/.octop/config.json" in error_message("CONFIG_FILE_CORRUPT", "en", **kwargs)
    assert "line 3, column 1" in error_message("CONFIG_FILE_CORRUPT", "zh", **kwargs)
    for locale in ("en", "zh"):
        msg = error_message("CONFIG_FILE_CORRUPT", locale, **kwargs)
        assert "{path}" not in msg and "{detail}" not in msg
