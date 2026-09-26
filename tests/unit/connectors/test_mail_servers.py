"""Unit tests for shared mailbox host resolution and qq-mail IMAP login."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from octop.infra.connectors import mail_servers
from octop.infra.connectors.gateway.adapters import qq_mail
from octop.infra.connectors.mail_servers import (
    correct_netease_imap_host,
    correct_netease_smtp_host,
    resolve_mail_servers,
)


@pytest.mark.parametrize(
    ("email", "provider", "imap_host", "smtp_host"),
    [
        ("a@163.com", "netease", "imap.163.com", "smtp.163.com"),
        ("a@126.com", "netease", "imap.126.com", "smtp.126.com"),
        ("a@yeah.net", "netease", "imap.yeah.net", "smtp.yeah.net"),
        ("a@qq.com", "qq", "imap.qq.com", "smtp.qq.com"),
        ("a@gmail.com", "gmail", "imap.gmail.com", "smtp.gmail.com"),
        # Domain alone is enough when provider is omitted.
        ("a@126.com", "", "imap.126.com", "smtp.126.com"),
    ],
)
def test_resolve_mail_servers(email: str, provider: str, imap_host: str, smtp_host: str) -> None:
    creds: dict[str, Any] = {"email": email, "password": "x"}
    if provider:
        creds["mail_provider"] = provider
    resolved = resolve_mail_servers(creds)
    assert resolved[0] == imap_host
    assert resolved[2] == smtp_host


def test_correct_netease_imap_host_fixes_legacy_163_for_126() -> None:
    assert correct_netease_imap_host("user@126.com", "imap.163.com") == "imap.126.com"
    assert correct_netease_imap_host("user@126.com", None) == "imap.126.com"
    assert correct_netease_imap_host("user@126.com", "") == "imap.126.com"


def test_correct_netease_imap_host_keeps_custom_non_netease() -> None:
    assert correct_netease_imap_host("user@126.com", "imap.example.com") == "imap.example.com"


def test_correct_netease_smtp_host_fixes_legacy() -> None:
    assert correct_netease_smtp_host("user@yeah.net", "smtp.163.com") == "smtp.yeah.net"


def test_should_send_imap_id_for_netease_host() -> None:
    imap = MagicMock()
    imap.capabilities = ()
    assert qq_mail._should_send_imap_id(imap, "imap.126.com") is True


def test_should_send_imap_id_when_capability_advertised() -> None:
    imap = MagicMock()
    imap.capabilities = ("IMAP4rev1", "ID")
    assert qq_mail._should_send_imap_id(imap, "imap.custom.example") is True


def test_should_not_send_imap_id_without_netease_or_capability() -> None:
    imap = MagicMock()
    imap.capabilities = ("IMAP4rev1",)
    assert qq_mail._should_send_imap_id(imap, "imap.qq.com") is False


def test_imap_login_sends_id_and_uses_corrected_host() -> None:
    fake_imap = MagicMock()
    fake_imap.capabilities = ("IMAP4rev1", "ID")
    fake_imap._simple_command.return_value = ("OK", [b"ID completed"])
    fake_imap.login.return_value = ("OK", [b"LOGIN completed"])

    with patch(
        "octop.infra.connectors.gateway.adapters.qq_mail.imaplib.IMAP4_SSL",
        return_value=fake_imap,
    ) as ssl_ctor:
        imap = qq_mail._imap_login(
            {
                "email": "user@126.com",
                "password": "auth-code",
                "imap_host": "imap.163.com",  # legacy wrong host
            }
        )

    assert imap is fake_imap
    ssl_ctor.assert_called_once_with(
        "imap.126.com",
        993,
        timeout=mail_servers.IMAP_CONNECT_TIMEOUT,
    )
    fake_imap._simple_command.assert_called_once()
    assert fake_imap._simple_command.call_args[0][0] == "ID"
    fake_imap.login.assert_called_once_with("user@126.com", "auth-code")


def test_imap_login_skips_id_for_qq() -> None:
    fake_imap = MagicMock()
    fake_imap.capabilities = ("IMAP4rev1",)
    fake_imap.login.return_value = ("OK", [b"LOGIN completed"])

    with patch(
        "octop.infra.connectors.gateway.adapters.qq_mail.imaplib.IMAP4_SSL",
        return_value=fake_imap,
    ):
        qq_mail._imap_login(
            {
                "email": "user@qq.com",
                "password": "auth-code",
                "imap_host": "imap.qq.com",
            }
        )

    fake_imap._simple_command.assert_not_called()
    fake_imap.login.assert_called_once_with("user@qq.com", "auth-code")


def _stub_inbox(uid_count: int) -> MagicMock:
    """IMAP stub whose INBOX holds *uid_count* messages, UIDs ascending (oldest first)."""
    imap = MagicMock()
    imap.select.return_value = ("OK", [str(uid_count).encode()])

    def uid(cmd: str, *args: Any) -> tuple[str, list[Any]]:
        if cmd == "search":
            joined = " ".join(str(i) for i in range(1, uid_count + 1))
            return ("OK", [joined.encode()])
        wanted = args[0].decode() if isinstance(args[0], bytes) else str(args[0])
        header = f"From: a@b.c\r\nSubject: mail {wanted}\r\nDate: X\r\n".encode()
        return ("OK", [(b"1 (BODY[HEADER.FIELDS (FROM SUBJECT DATE)]", header)])

    imap.uid.side_effect = uid
    return imap


def _search_uids(imap: MagicMock, **args: Any) -> list[str]:
    with patch(
        "octop.infra.connectors.gateway.adapters.qq_mail.imaplib.IMAP4_SSL",
        return_value=imap,
    ):
        rows = json.loads(qq_mail._email_search({}, args))
    return [str(row["uid"]) for row in rows]


def test_search_emails_caps_and_repairs_out_of_range_limit() -> None:
    """``uids[-limit:]`` inverts a negative limit, so ``limit`` must be clamped first.

    ``search_emails`` is model-facing and ``limit`` arrived unbounded: ``-5`` became
    "drop the 5 oldest" and returned 7, and ``-100`` answered "no mail" on a
    populated inbox. Clamping into ``1.._MAX_SEARCH_LIMIT`` matches what the sibling
    adapters (``tencent_ima``, ``tencent_news``, ``yuandian``, ``weknora``) already do.
    """
    newest_first = ["12", "11", "10", "9", "8", "7", "6", "5", "4", "3", "2", "1"]

    imap = _stub_inbox(12)
    assert _search_uids(imap, query="ALL", limit=5) == newest_first[:5]
    assert imap.uid.call_count == 6  # one search + five fetches

    imap = _stub_inbox(12)
    assert _search_uids(imap, query="ALL", limit=-5) == ["12"]
    assert imap.uid.call_count == 2  # was 7 fetches for a "max 5" request

    imap = _stub_inbox(12)
    assert _search_uids(imap, query="ALL", limit=-100) == ["12"]  # was: no mail at all

    imap = _stub_inbox(12)
    assert _search_uids(imap, query="ALL", limit=500) == newest_first
    assert imap.uid.call_count == 13  # a request past the mailbox still costs one fetch each

    big_inbox = _stub_inbox(60)
    assert len(_search_uids(big_inbox, query="ALL", limit=500)) == qq_mail._MAX_SEARCH_LIMIT
    assert big_inbox.uid.call_count == 51  # 1 search + 50, not 60


def test_search_emails_advertises_the_bounds_it_enforces() -> None:
    tool = next(t for t in qq_mail.TOOLS if t["name"] == "search_emails")
    limit = tool["inputSchema"]["properties"]["limit"]
    assert limit["minimum"] == 1
    assert limit["maximum"] == qq_mail._MAX_SEARCH_LIMIT
