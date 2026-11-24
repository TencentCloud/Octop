"""Blank secrets stay stored and stay off the API payload."""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import BaseModel

from octop.infra.db.repos.backends import BackendRow
from octop.infra.utils.secret_fields import (
    Secret,
    blank_secret,
    merge_blank_secrets,
    merge_config_json,
    model_secret_names,
    persisted_secret,
    redact_config_json,
    redact_mapping,
)


class _StorageBody(BaseModel):
    endpoint: str | None = None
    access_key: Annotated[str | None, Secret()] = None
    secret_key: Annotated[str | None, Secret()] = None
    api_key: str | None = None


def test_model_fields_follow_the_marker_not_the_name() -> None:
    assert model_secret_names(_StorageBody) == {"access_key", "secret_key"}
    payload = {
        "endpoint": "tos.example",
        "access_key": "AKIDxxxx",
        "secret_key": "secret-value",
        "api_key": "sk-live",
        "bot_token": "tok",
    }
    kept, present = redact_mapping(payload, model=_StorageBody)
    assert kept == {"endpoint": "tos.example", "api_key": "sk-live"}
    assert present == ["access_key", "secret_key", "bot_token"]

    merged = merge_blank_secrets(
        {"access_key": "AKID********", "api_key": "", "bot_token": ""},
        {"access_key": "stored-ak", "api_key": "stored-sk", "bot_token": "stored-tok"},
        model=_StorageBody,
    )
    assert merged["access_key"] == "stored-ak"
    assert merged["api_key"] == ""
    assert "bot_token" not in merged


def test_persisted_secret_keeps_blank_marked_fields() -> None:
    body = _StorageBody(access_key="AKID********", secret_key="new-secret")
    assert persisted_secret(body, "access_key") is None
    assert persisted_secret(body, "secret_key") == "new-secret"


def test_redact_mapping_drops_secrets_and_lists_them() -> None:
    kept, present = redact_mapping({"app_id": "cli", "app_secret": "secret", "bot_token": "tok"})
    assert kept == {"app_id": "cli"}
    assert present == ["app_secret", "bot_token"]


def test_merge_blank_secrets_keeps_stored_and_prefers_typed() -> None:
    merged = merge_blank_secrets(
        {"app_id": "cli"},
        {"app_id": "old", "app_secret": "stored"},
    )
    assert merged["app_id"] == "cli"
    assert merged["app_secret"] == "stored"

    masked = merge_blank_secrets(
        {"app_secret": "AKID********"},
        {"app_secret": "stored"},
    )
    assert masked["app_secret"] == "stored"

    replaced = merge_blank_secrets(
        {"app_secret": "new"},
        {"app_secret": "stored"},
    )
    assert replaced["app_secret"] == "new"


def test_merge_blank_secrets_clears_explicitly_emptied_secret() -> None:
    for cleared in ("", "  ", None):
        merged = merge_blank_secrets(
            {"app_id": "cli", "app_secret": cleared},
            {"app_id": "old", "app_secret": "stored"},
        )
        assert merged["app_id"] == "cli"
        assert "app_secret" not in merged


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

    cleared = merge_config_json(json.dumps({"security_token": ""}), stored)
    assert cleared is not None
    assert "security_token" not in json.loads(cleared)


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
