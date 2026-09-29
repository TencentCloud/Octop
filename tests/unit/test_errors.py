"""tests/unit/test_errors.py"""

from __future__ import annotations

import pytest

from octop.infra.errors import ErrorCode, OctopError


def test_octop_error_carries_code_and_status():
    err = OctopError(ErrorCode.AGENT_NOT_FOUND, "missing", details={"id": "a"})
    assert err.code is ErrorCode.AGENT_NOT_FOUND
    assert err.status == 404
    assert err.message == "missing"
    assert err.details == {"id": "a"}


def test_octop_error_default_status_for_known_code():
    err = OctopError(ErrorCode.FORBIDDEN, "nope")
    assert err.status == 403


def test_octop_error_to_envelope():
    err = OctopError(ErrorCode.AUTH_FAILED, "bad creds")
    assert err.to_envelope() == {
        "error": {"code": "AUTH_FAILED", "message": "bad creds", "details": {}}
    }


def test_octop_error_to_envelope_localized():
    err = OctopError(ErrorCode.TOKEN_EXPIRED, "token expired")
    assert err.to_envelope(locale="zh")["error"]["message"] == "登录已过期，请重新登录。"


def test_unknown_error_code_rejected():
    with pytest.raises(ValueError):
        ErrorCode("NOT_A_CODE")


def test_every_code_survives_a_details_key_named_code() -> None:
    """A `details["code"]` must not collide with `error_message`'s own parameter.

    G6's graph refusal carries `details={"code": <one of four>}` -- that key is part of
    its contract -- and `error_message(code, locale, **kwargs)` owns the name `code`, so
    the refusal raised `TypeError` **at serialization time** and could never reach a
    client. Swept over **every** code, not just that one: the fault was the class, not
    the site. The key must still be in the envelope (dropping it would trade a 500 for a
    broken contract).
    """
    for code in ErrorCode:
        err = OctopError(
            code, "message", details={"code": "missing-id", "path": ["a", "b"], "locale": "x"}
        )
        envelope = err.to_envelope(locale="zh")
        assert envelope["error"]["code"] == code.value
        assert envelope["error"]["details"]["code"] == "missing-id"
        assert envelope["error"]["details"]["path"] == ["a", "b"]
        assert envelope["error"]["details"]["locale"] == "x"
