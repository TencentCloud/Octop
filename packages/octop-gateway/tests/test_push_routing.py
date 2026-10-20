"""Tests for proactive push routing helpers."""

from __future__ import annotations

from octop_gateway.push_routing import (
    EPHEMERAL_PUSH_META,
    alias_subject_fields,
    strip_ephemeral_push_meta,
)


def test_alias_subject_fields_backfills_missing_keys() -> None:
    meta: dict[str, str] = {}
    alias_subject_fields(meta, "openid_1", "user_openid", "chat_id")
    assert meta == {"user_openid": "openid_1", "chat_id": "openid_1"}


def test_alias_subject_fields_does_not_overwrite() -> None:
    meta = {"chat_id": "existing"}
    alias_subject_fields(meta, "openid_1", "chat_id", "user_openid")
    assert meta == {"chat_id": "existing", "user_openid": "openid_1"}


def test_strip_ephemeral_push_meta_removes_webhook_and_reply_context() -> None:
    meta = {
        "chat_id": "c1",
        "msg_id": "m1",
        "webhook_url": "https://example.com/hook",
        "context_token": "ctx",
    }
    strip_ephemeral_push_meta(meta)
    assert meta == {"chat_id": "c1"}
    assert "webhook_url" in EPHEMERAL_PUSH_META
