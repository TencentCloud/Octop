"""QQ mail and other IMAP/SMTP mailbox gateway."""

from __future__ import annotations

import contextlib
import email
import imaplib
import json
import smtplib
from email.mime.text import MIMEText
from typing import Any

TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_emails",
        "description": "Search recent emails in INBOX (IMAP)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "IMAP search criteria, default ALL",
                },
                "limit": {"type": "integer", "description": "Max messages, default 10"},
            },
        },
    },
    {
        "name": "read_email",
        "description": "Read a single email body by UID",
        "inputSchema": {
            "type": "object",
            "properties": {
                "uid": {"type": "string", "description": "IMAP UID"},
            },
            "required": ["uid"],
        },
    },
    {
        "name": "send_email",
        "description": "Send a plain-text email via SMTP",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        },
    },
]


def list_tools() -> list[dict[str, Any]]:
    return TOOLS


def call_tool(creds: dict[str, Any], name: str, args: dict[str, Any]) -> str:
    if name == "search_emails":
        return _email_search(creds, args)
    if name == "read_email":
        return _email_read(creds, args)
    if name == "send_email":
        return _email_send(creds, args)
    raise ValueError(f"unknown tool: {name}")


def _email_search(creds: dict[str, Any], args: dict[str, Any]) -> str:
    query = str(args.get("query") or "ALL")
    limit = int(args.get("limit") or 10)
    imap = _imap_login(creds)
    try:
        imap.select("INBOX")
        _typ, data = imap.uid("search", "UTF-8", query)
        uids = (data[0] or b"").split()
        uids = uids[-limit:]
        out: list[dict[str, str]] = []
        for uid in reversed(uids):
            _typ, msg_data = imap.uid(
                "fetch", uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])"
            )
            if not msg_data or not msg_data[0]:
                continue
            hdr = email.message_from_bytes(msg_data[0][1])
            out.append(
                {
                    "uid": uid.decode(),
                    "from": hdr.get("From", ""),
                    "subject": hdr.get("Subject", ""),
                    "date": hdr.get("Date", ""),
                }
            )
        return json.dumps(out, ensure_ascii=False, indent=2)
    finally:
        with contextlib.suppress(Exception):
            imap.logout()


def _email_read(creds: dict[str, Any], args: dict[str, Any]) -> str:
    uid = str(args.get("uid") or "").strip()
    if not uid:
        raise ValueError("uid is required")
    imap = _imap_login(creds)
    try:
        imap.select("INBOX")
        _typ, msg_data = imap.uid("fetch", uid, "(RFC822)")
        if not msg_data or not msg_data[0]:
            raise ValueError(f"email uid {uid} not found")
        msg = email.message_from_bytes(msg_data[0][1])
        body = _extract_body(msg)
        return json.dumps(
            {
                "uid": uid,
                "from": msg.get("From", ""),
                "subject": msg.get("Subject", ""),
                "date": msg.get("Date", ""),
                "body": body,
            },
            ensure_ascii=False,
            indent=2,
        )
    finally:
        with contextlib.suppress(Exception):
            imap.logout()


def _email_send(creds: dict[str, Any], args: dict[str, Any]) -> str:
    to_addr = str(args.get("to") or "").strip()
    subject = str(args.get("subject") or "")
    body = str(args.get("body") or "")
    if not to_addr:
        raise ValueError("to is required")
    from_addr = str(creds.get("email") or "")
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    host = str(creds.get("smtp_host") or "smtp.qq.com")
    port = int(creds.get("smtp_port") or 587)
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(from_addr, str(creds.get("password") or ""))
        smtp.send_message(msg)
    return json.dumps({"ok": True, "to": to_addr}, ensure_ascii=False)


def _imap_login(creds: dict[str, Any]) -> imaplib.IMAP4_SSL:
    host = str(creds.get("imap_host") or "imap.qq.com")
    port = int(creds.get("imap_port") or 993)
    user = str(creds.get("email") or "")
    password = str(creds.get("password") or "")
    imap: imaplib.IMAP4_SSL = imaplib.IMAP4_SSL(host, port)
    imap.login(user, password)
    return imap


def probe_credentials(creds: dict[str, Any]) -> None:
    """Validate mailbox credentials via IMAP login."""
    imap = _imap_login(creds)
    with contextlib.suppress(Exception):
        imap.logout()


def _extract_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        return ""
    payload = msg.get_payload(decode=True)
    if isinstance(payload, bytes):
        return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return str(payload or "")
