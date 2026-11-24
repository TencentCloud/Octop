"""Blank secrets stay stored and stay off the API payload."""

from __future__ import annotations

import json

from octop.infra.db.repos.backends import BackendRow
from octop.infra.utils.secret_fields import (
    blank_secret,
    merge_blank_secrets,
    merge_config_json,
    redact_config_json,
    redact_mapping,
)


def test_redact_mapping_drops_secrets_and_lists_them() -> None:
    kept, present = redact_mapping({"app_id": "cli", "app_secret": "secret", "bot_token": "tok"})
    assert kept == {"app_id": "cli"}
    assert present == ["app_secret", "bot_token"]


def test_merge_blank_secrets_keeps_stored_and_prefers_typed() -> None:
    merged = merge_blank_secrets(
        {"app_id": "cli", "app_secret": ""},
        {"app_id": "old", "app_secret": "stored"},
    )
    assert merged["app_id"] == "cli"
    assert merged["app_secret"] == "stored"

    replaced = merge_blank_secrets(
        {"app_secret": "new"},
        {"app_secret": "stored"},
    )
    assert replaced["app_secret"] == "new"


def test_blank_secret_treats_mask_as_unchanged() -> None:
    assert blank_secret(None)
    assert blank_secret("")
    assert blank_secret("AKID********")
    assert not blank_secret("AKIDrealvalue")


def test_config_json_round_trip_keeps_security_token() -> None:
    stored = json.dumps({"prefix": "agents", "security_token": "sts-secret"})
    redacted, present = redact_config_json(stored)
    assert present == ["security_token"]
    assert redacted is not None
    assert "sts-secret" not in redacted
    assert json.loads(redacted)["prefix"] == "agents"

    merged = merge_config_json(redacted, stored)
    assert merged is not None
    assert json.loads(merged)["security_token"] == "sts-secret"


def test_storage_row_omits_secret_key_and_config_token() -> None:
    from octop.api.routers.storage_backends import _row_to_dict

    row = BackendRow(
        id=1,
        name="tos",
        kind="tos",
        endpoint="tos.example",
        access_key="AKIDxxxx",
        secret_key="secret-value",
        bucket="bucket",
        region="cn-beijing",
        config_json=json.dumps({"security_token": "sts-secret", "prefix": "a"}),
        note=None,
        enabled=1,
        created_at=0,
        updated_at=0,
    )
    payload = _row_to_dict(row)
    assert "secret_key" not in payload
    assert payload["secret_key_set"] is True
    assert payload["access_key"] == "AKID********"
    assert "sts-secret" not in (payload["config_json"] or "")
    assert payload["config_secrets_set"] == ["security_token"]
