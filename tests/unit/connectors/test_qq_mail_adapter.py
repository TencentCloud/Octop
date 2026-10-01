"""Regression tests for qq-mail header/body decoding (JSON-safety).

Covers the crash reported in TECH-REPORT-qq-mail-header-bug.md:
``email.message_from_bytes`` under the default compat32 policy returns
``email.header.Header`` objects for header fields carrying raw non-ASCII
bytes, and ``search_emails`` / ``read_email`` used to feed those straight
into ``json.dumps`` → ``TypeError: Object of type Header is not JSON
serializable``.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from octop.infra.connectors.gateway.adapters import qq_mail

_CREDS: dict[str, Any] = {
    "email": "user@example.com",
    "password": "auth-code",
    "imap_host": "imap.example.com",
}


def _fake_imap_with_messages(messages: dict[bytes, bytes]) -> MagicMock:
    """IMAP4_SSL mock: UID search returns the keys of *messages* (newest first
    via reversed()), UID fetch returns the raw RFC822-ish bytes."""

    def uid(command: str, *args: object) -> tuple[str, list[Any]]:
        if command == "search":
            data = b" ".join(sorted(messages.keys(), key=int))
            return "OK", [data]
        if command == "fetch":
            arg = args[0]
            target = arg if isinstance(arg, bytes) else str(arg).encode()
            raw = messages[target]
            return "OK", [(b"header", raw), b")"]
        raise AssertionError(f"unexpected uid command: {command}")

    fake = MagicMock()
    fake.uid.side_effect = uid
    return fake


# ---------------------------------------------------------------------------
# _email_search: the reported 100%-crash path
# ---------------------------------------------------------------------------


def test_search_emails_raw_utf8_headers_do_not_crash_json() -> None:
    """Bare non-ASCII header bytes (no MIME encoding) must serialize."""
    raw = (
        "From: 张三 <a@b.com>\r\n"
        "Subject: 测试邮件\r\n"
        "Date: Wed, 30 Sep 2026 10:00:00 +0800\r\n"
        "\r\n"
        "body"
    ).encode()
    fake = _fake_imap_with_messages({b"30": raw})

    with patch(
        "octop.infra.connectors.gateway.adapters.qq_mail.imaplib.IMAP4_SSL",
        return_value=fake,
    ):
        result = qq_mail.call_tool(_CREDS, "search_emails", {})

    rows = json.loads(result)
    assert len(rows) == 1
    assert rows[0]["uid"] == "30"
    assert rows[0]["from"] == "张三 <a@b.com>"
    assert rows[0]["subject"] == "测试邮件"
    assert rows[0]["date"].startswith("Wed, 30 Sep 2026")


def test_search_emails_ascii_headers_unchanged() -> None:
    raw = (
        b"From: Alice <a@b.com>\r\n"
        b"Subject: test email\r\n"
        b"Date: Wed, 30 Sep 2026 10:00:00 +0800\r\n"
        b"\r\n"
        b"body"
    )
    fake = _fake_imap_with_messages({b"1": raw})

    with patch(
        "octop.infra.connectors.gateway.adapters.qq_mail.imaplib.IMAP4_SSL",
        return_value=fake,
    ):
        result = qq_mail.call_tool(_CREDS, "search_emails", {})

    rows = json.loads(result)
    assert rows[0]["from"] == "Alice <a@b.com>"
    assert rows[0]["subject"] == "test email"


def test_search_emails_mime_encoded_words_render_readable() -> None:
    """Bonus of policy.default: encoded words decode to readable text."""
    raw = (
        b"From: =?utf-8?q?=E5=BC=A0=E4=B8=89?= <a@b.com>\r\n"
        b"Subject: =?utf-8?q?=E6=B5=8B=E8=AF=95?=\r\n"
        b"\r\n"
        b"body"
    )
    fake = _fake_imap_with_messages({b"7": raw})

    with patch(
        "octop.infra.connectors.gateway.adapters.qq_mail.imaplib.IMAP4_SSL",
        return_value=fake,
    ):
        result = qq_mail.call_tool(_CREDS, "search_emails", {})

    rows = json.loads(result)
    assert rows[0]["from"] == "张三 <a@b.com>"
    assert rows[0]["subject"] == "测试"


# ---------------------------------------------------------------------------
# _email_read: same header defect + unknown-charset body
# ---------------------------------------------------------------------------


def test_read_email_raw_utf8_headers_and_unknown_charset_body() -> None:
    """Headers with raw UTF-8 plus a body declaring an unknown charset both
    must degrade gracefully instead of raising TypeError/LookupError."""
    raw = (
        "From: 张三 <a@b.com>\r\n"
        "Subject: 测试邮件\r\n"
        'Content-Type: text/plain; charset="unknown-8bit"\r\n'
        "\r\n"
        "正文内容"
    ).encode()
    fake = _fake_imap_with_messages({b"30": raw})

    with patch(
        "octop.infra.connectors.gateway.adapters.qq_mail.imaplib.IMAP4_SSL",
        return_value=fake,
    ):
        result = qq_mail.call_tool(_CREDS, "read_email", {"uid": "30"})

    rec = json.loads(result)
    assert rec["from"] == "张三 <a@b.com>"
    assert rec["subject"] == "测试邮件"
    # UTF-8 fallback for the bogus declared charset
    assert rec["body"] == "正文内容"


def test_read_email_ascii_message_unchanged() -> None:
    raw = (
        b"From: Alice <a@b.com>\r\n"
        b"Subject: hello\r\n"
        b'Content-Type: text/plain; charset="utf-8"\r\n'
        b"\r\n"
        b"plain body"
    )
    fake = _fake_imap_with_messages({b"1": raw})

    with patch(
        "octop.infra.connectors.gateway.adapters.qq_mail.imaplib.IMAP4_SSL",
        return_value=fake,
    ):
        result = qq_mail.call_tool(_CREDS, "read_email", {"uid": "1"})

    rec = json.loads(result)
    assert rec["from"] == "Alice <a@b.com>"
    assert rec["body"] == "plain body"


# ---------------------------------------------------------------------------
# Unit-level: parsing helpers
# ---------------------------------------------------------------------------


def test_parse_message_never_returns_header_objects() -> None:
    """The exact regression from the report: compat32 returned Header here."""
    raw = "From: 张三 <a@b.com>\r\nSubject: 测试邮件\r\n\r\n".encode()
    msg = qq_mail._parse_message(raw)

    value = msg.get("From", "")
    assert isinstance(value, str), f"expected str, got {type(value).__name__}"

    # And the whole search-shaped record must be serializable.
    record = {"from": qq_mail._safe_header(msg, "From")}
    assert json.dumps(record, ensure_ascii=False)


def test_parse_message_survives_broken_mime_words() -> None:
    raw = b"Subject: =?utf-8?q?=E6=B5=8B\r\n\r\nbody"
    msg = qq_mail._parse_message(raw)

    assert isinstance(qq_mail._safe_header(msg, "Subject"), str)


def test_extract_body_falls_back_to_utf8_on_unknown_charset() -> None:
    raw = b'Content-Type: text/plain; charset="unknown-8bit"\r\n\r\n' + "正文内容".encode()
    msg = qq_mail._parse_message(raw)

    assert qq_mail._extract_body(msg) == "正文内容"


def test_extract_body_multipart_plain_part() -> None:
    raw = (
        b'Content-Type: multipart/mixed; boundary="X"\r\n'
        b"\r\n"
        b"--X\r\n"
        b'Content-Type: text/plain; charset="utf-8"\r\n'
        b"\r\n"
        b"hello\r\n"
        b"--X--\r\n"
    )
    msg = qq_mail._parse_message(raw)

    assert qq_mail._extract_body(msg) == "hello"


def test_safe_header_missing_field_returns_empty_string() -> None:
    msg = qq_mail._parse_message(b"From: a@b.com\r\n\r\n")
    assert qq_mail._safe_header(msg, "Subject") == ""


@pytest.mark.parametrize(
    "field",
    ["From", "Subject", "Date"],
)
def test_safe_header_always_plain_str(field: str) -> None:
    raw = "From: 张三 <a@b.com>\r\nSubject: 测试\r\nDate: Wed, 30 Sep 2026 10:00:00\r\n".encode()
    msg = qq_mail._parse_message(raw)
    value = qq_mail._safe_header(msg, field)
    assert type(value) is str
