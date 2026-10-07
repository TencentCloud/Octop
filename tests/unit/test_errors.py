"""tests/unit/test_errors.py"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from octop.infra.errors import ErrorCode, OctopError

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOC_ROW = re.compile(r"^\|\s*`([A-Z][A-Z0-9_]+)`\s*\|\s*(\d{3})\s*\|")


def _api_doc_error_rows() -> list[tuple[str, int]]:
    lines = (_REPO_ROOT / "docs" / "api.md").read_text(encoding="utf-8").splitlines()
    start = lines.index("## Error envelope")
    end = next(
        (i for i, line in enumerate(lines[start + 1 :], start + 1) if line.startswith("## ")),
        len(lines),
    )
    return [
        (match.group(1), int(match.group(2)))
        for line in lines[start:end]
        if (match := _DOC_ROW.match(line))
    ]


def test_api_doc_error_table_lists_real_codes_with_real_statuses():
    rows = _api_doc_error_rows()
    assert rows, "docs/api.md error table was not parsed"
    for code, documented_status in rows:
        assert code in ErrorCode.__members__, f"docs/api.md lists {code}, which is not an ErrorCode"
        status = OctopError(ErrorCode[code], "probe").status
        assert status == documented_status, (
            f"docs/api.md lists {code} as {documented_status}, the server returns {status}"
        )


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
