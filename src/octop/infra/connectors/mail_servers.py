"""Shared IMAP/SMTP host presets for mailbox connectors."""

from __future__ import annotations

from typing import Any

MailServers = tuple[str, int, str, int]  # imap_host, imap_port, smtp_host, smtp_port

_MAIL_PROVIDER_PRESETS: dict[str, MailServers] = {
    "qq": ("imap.qq.com", 993, "smtp.qq.com", 587),
    "gmail": ("imap.gmail.com", 993, "smtp.gmail.com", 587),
}

# 163 / 126 / yeah 各用独立主机；混用会报 LOGIN 失败。
_NETEASE_DOMAIN_SERVERS: dict[str, MailServers] = {
    "163.com": ("imap.163.com", 993, "smtp.163.com", 587),
    "126.com": ("imap.126.com", 993, "smtp.126.com", 587),
    "yeah.net": ("imap.yeah.net", 993, "smtp.yeah.net", 587),
}
_NETEASE_DEFAULT_SERVERS = _NETEASE_DOMAIN_SERVERS["163.com"]

NETEASE_IMAP_HOSTS = frozenset(servers[0] for servers in _NETEASE_DOMAIN_SERVERS.values())
NETEASE_SMTP_HOSTS = frozenset(servers[2] for servers in _NETEASE_DOMAIN_SERVERS.values())

DEFAULT_IMAP_HOST = "imap.qq.com"
DEFAULT_SMTP_HOST = "smtp.qq.com"
IMAP_CONNECT_TIMEOUT = 30


def _email_domain(email: str) -> str:
    text = email.strip().lower()
    return text.rsplit("@", 1)[-1] if "@" in text else ""


def netease_servers_for_email(email: str) -> MailServers:
    domain = _email_domain(email)
    return _NETEASE_DOMAIN_SERVERS.get(domain, _NETEASE_DEFAULT_SERVERS)


def preferred_netease_imap_host(email: str) -> str | None:
    domain = _email_domain(email)
    servers = _NETEASE_DOMAIN_SERVERS.get(domain)
    return servers[0] if servers else None


def preferred_netease_smtp_host(email: str) -> str | None:
    domain = _email_domain(email)
    servers = _NETEASE_DOMAIN_SERVERS.get(domain)
    return servers[2] if servers else None


def resolve_mail_servers(credentials: dict[str, Any]) -> MailServers:
    """Resolve IMAP/SMTP hosts from mail_provider and/or email domain."""
    provider = str(credentials.get("mail_provider") or "").strip().lower()
    email = str(credentials.get("email") or "").strip().lower()
    domain = _email_domain(email)

    if provider == "netease" or domain in _NETEASE_DOMAIN_SERVERS:
        return netease_servers_for_email(email)
    if provider in _MAIL_PROVIDER_PRESETS:
        return _MAIL_PROVIDER_PRESETS[provider]
    if domain in ("qq.com", "foxmail.com"):
        return _MAIL_PROVIDER_PRESETS["qq"]
    if domain == "gmail.com":
        return _MAIL_PROVIDER_PRESETS["gmail"]

    return (
        str(credentials.get("imap_host") or DEFAULT_IMAP_HOST),
        int(credentials.get("imap_port") or 993),
        str(credentials.get("smtp_host") or DEFAULT_SMTP_HOST),
        int(credentials.get("smtp_port") or 587),
    )


def correct_netease_imap_host(email: str, stored_host: str | None) -> str:
    """Fix legacy NetEase hosts (e.g. 126 stored as imap.163.com)."""
    host = str(stored_host or "").strip()
    preferred = preferred_netease_imap_host(email)
    if preferred and (not host or host in NETEASE_IMAP_HOSTS):
        return preferred
    return host or DEFAULT_IMAP_HOST


def correct_netease_smtp_host(email: str, stored_host: str | None) -> str:
    """Fix legacy NetEase SMTP hosts the same way as IMAP."""
    host = str(stored_host or "").strip()
    preferred = preferred_netease_smtp_host(email)
    if preferred and (not host or host in NETEASE_SMTP_HOSTS):
        return preferred
    return host or DEFAULT_SMTP_HOST
