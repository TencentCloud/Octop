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


# ── PROJECT_TASK_THREAD_NOT_FOUND: zh is asserted explicitly ─────────────────
#
# ``loader.lookup`` falls back to English when a zh key is missing, so an en-only
# check would stay green while zh users read English. The zh value below is frozen
# by PLAN.md §7 / SPEC.md §边界与禁止项.


def test_project_task_thread_not_found_zh_is_frozen():
    assert error_message("PROJECT_TASK_THREAD_NOT_FOUND", "zh") == "关联会话不存在，无法创建任务"


def test_dashboard_api_error_zh_carries_the_same_frozen_text():
    repo = Path(__file__).resolve().parents[3]
    dash_zh = json.loads((repo / "dashboard/src/locales/zh.json").read_text(encoding="utf-8"))
    assert dash_zh["apiErrors"]["PROJECT_TASK_THREAD_NOT_FOUND"] == error_message(
        "PROJECT_TASK_THREAD_NOT_FOUND", "zh"
    )


def test_api_errors_namespaces_agree_in_both_locales():
    """The ``errors`` / ``apiErrors`` namespaces only — never the whole tree.

    Dashboard en/zh key trees differ outside these namespaces by design, so a
    whole-file equality assertion would be a false failure.
    """
    repo = Path(__file__).resolve().parents[3]
    for locale in ("en", "zh"):
        dash = json.loads(
            (repo / f"dashboard/src/locales/{locale}.json").read_text(encoding="utf-8")
        )
        backend = json.loads((repo / f"src/octop/i18n/{locale}.json").read_text(encoding="utf-8"))
        assert set(dash["apiErrors"]) == set(backend["errors"]) == {c.value for c in ErrorCode}


def test_backend_locales_have_identical_key_trees():
    repo = Path(__file__).resolve().parents[3]
    en = json.loads((repo / "src/octop/i18n/en.json").read_text(encoding="utf-8"))
    zh = json.loads((repo / "src/octop/i18n/zh.json").read_text(encoding="utf-8"))

    def tree(value: object) -> object:
        return {k: tree(v) for k, v in value.items()} if isinstance(value, dict) else True

    assert tree(en) == tree(zh)


def test_dashboard_chat_labels_are_paired_and_localized():
    """The four S0/T2.6 labels — namespace-level parity, frozen zh wording."""
    repo = Path(__file__).resolve().parents[3]
    en = json.loads((repo / "dashboard/src/locales/en.json").read_text(encoding="utf-8"))
    zh = json.loads((repo / "dashboard/src/locales/zh.json").read_text(encoding="utf-8"))
    assert set(en["chat"]) == set(zh["chat"])
    assert len(zh["chat"]) == 211
    assert zh["chat"]["sectionPinned"] == "置顶"
    assert zh["chat"]["sectionActive"] == "会话"
    assert zh["chat"]["sectionUnused"] == "未使用"
    assert zh["chat"]["projectSessionBadge"] == "项目会话"
    assert en["chat"]["sectionPinned"] == "Pinned"
    assert en["chat"]["sectionActive"] == "Chats"
    assert en["chat"]["sectionUnused"] == "Unused"
    assert en["chat"]["projectSessionBadge"] == "Project chat"
