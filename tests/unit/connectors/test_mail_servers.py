"""Unit tests for shared mailbox host resolution and qq-mail IMAP login."""

from __future__ import annotations

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
