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


def test_downstream_credential_errors_are_bad_request():
    # Peer / connector / channel credential rejections are client input errors (400),
    # not local session authentication failures (401).
    assert OctopError(ErrorCode.BRIDGE_AUTH_FAILED, "bad peer creds").status == 400
    assert OctopError(ErrorCode.CHANNEL_INVALID_CREDENTIALS, "bad channel creds").status == 400
    assert OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, "bad connector creds").status == 400

    # Local session auth errors must remain 401.
    assert OctopError(ErrorCode.AUTH_FAILED, "bad session").status == 401
    assert OctopError(ErrorCode.TOKEN_EXPIRED, "expired").status == 401

