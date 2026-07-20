"""Live round-trip tests against real object-storage backends (COS / S3 / OSS / OBS).

These exercise the *real* product code path:

* :func:`octop.infra.backend.probe.probe_storage_backend` is exactly what the
  dashboard calls when a user adds / verifies a storage backend — so a green
  probe means real credentials are accepted by the real mapping.
* A boto3 put/get/delete round-trip proves end-to-end read/write on the bucket.

Multiple backends are probed in a single run. Each backend reads its own
env-var *prefix*; when a backend's required vars are absent, ONLY that
backend's cases auto-skip, so CI without secrets stays green.

Prefixes (repo-root ``.env``, loaded by ``tests/live/conftest.py``):
  OSS_        → Tencent COS      (OSS_KIND=cos)
  ALI_OSS_    → Aliyun OSS       (ALI_OSS_KIND=oss)

Run locally::

    uv run pytest tests/live/test_oss_storage.py -m live -v
"""

from __future__ import annotations

import uuid

import boto3
import pytest
from botocore.config import Config
from tests.support.secrets import optional_env, require_env

from octop.infra.backend.adapter import row_to_backend_spec
from octop.infra.backend.probe import probe_storage_backend, row_for_probe

pytestmark = pytest.mark.live

# Each backend reads its own env-var prefix. A backend is probed only when ALL
# of its required vars are present; otherwise only that backend's cases skip.
# `signature_version` selects the S3 sig scheme: Aliyun OSS rejects boto3's v4
# chunked ("aws-chunked") uploads, so it falls back to the V2 scheme; COS/S3 use
# the default v4 with a fully-signed body.
_BACKENDS: list[dict[str, str | None]] = [
    {"label": "cos", "prefix": "OSS_", "default_kind": "cos", "signature_version": None},
    {"label": "aliyun-oss", "prefix": "ALI_OSS_", "default_kind": "oss", "signature_version": "s3"},
]


def _load_backend(prefix: str, default_kind: str) -> object:
    """Build a BackendRow from a prefixed env; skip if credentials absent."""
    endpoint = optional_env(f"{prefix}ENDPOINT")
    access_key = optional_env(f"{prefix}ACCESS_KEY")
    secret_key = optional_env(f"{prefix}SECRET_KEY")
    bucket = optional_env(f"{prefix}BUCKET")
    if not (endpoint and access_key and secret_key and bucket):
        pytest.skip(f"set {prefix}ENDPOINT/ACCESS_KEY/SECRET_KEY/BUCKET to run")
    return row_for_probe(
        kind=optional_env(f"{prefix}KIND", default_kind) or default_kind,
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        bucket=bucket,
        region=optional_env(f"{prefix}REGION"),
    )


@pytest.mark.parametrize("backend", _BACKENDS, ids=lambda b: b["label"])
def test_oss_probe_accepts_real_credentials(backend: dict[str, str]) -> None:
    """The real backend probe must succeed with valid credentials."""
    result = probe_storage_backend(_load_backend(backend["prefix"], backend["default_kind"]))
    assert result.get("ok") is True, result


@pytest.mark.parametrize("backend", _BACKENDS, ids=lambda b: b["label"])
def test_oss_spec_mapping_is_complete(backend: dict[str, str]) -> None:
    """The DB row must map to a non-empty harness backend spec."""
    spec = row_to_backend_spec(_load_backend(backend["prefix"], backend["default_kind"]))
    assert spec is not None
    assert spec.get("type")
    assert spec.get("bucket")


@pytest.mark.parametrize("backend", _BACKENDS, ids=lambda b: b["label"])
def test_oss_roundtrip_put_get_delete(backend: dict[str, str]) -> None:
    """End-to-end write/read/delete on the real bucket (auto-cleaned)."""
    prefix = backend["prefix"]
    endpoint = require_env(f"{prefix}ENDPOINT")
    bucket = require_env(f"{prefix}BUCKET")
    key_prefix = optional_env(f"{prefix}PREFIX", "").strip().lstrip("/")
    key = f"{key_prefix}octop-live-test/{uuid.uuid4().hex}/hello.txt"

    sig = backend.get("signature_version")
    s3_cfg: dict[str, object] = {"addressing_style": "virtual"}
    # Aliyun OSS rejects boto3's v4 chunked ("aws-chunked") uploads; the V2
    # scheme avoids chunked encoding entirely and is accepted by Aliyun.
    if sig is None:
        s3_cfg["payload_signature_version"] = "s3v4"
    client = boto3.client(
        "s3",
        endpoint_url=endpoint if "://" in endpoint else f"https://{endpoint}",
        aws_access_key_id=require_env(f"{prefix}ACCESS_KEY"),
        aws_secret_access_key=require_env(f"{prefix}SECRET_KEY"),
        region_name=optional_env(f"{prefix}REGION") or None,
        config=Config(signature_version=sig, s3=s3_cfg),
    )
    client.put_object(Bucket=bucket, Key=key, Body=b"ping")
    try:
        body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
        assert body == b"ping"
    finally:
        client.delete_object(Bucket=bucket, Key=key)
