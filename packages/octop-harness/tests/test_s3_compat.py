"""S3-compatible client settings and ListObjects fallback."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from octop_harness.backends.s3_backend import (
    S3Backend,
    S3Config,
    _compat_s3_client_config,
    _is_s3_not_implemented,
)
from octop_harness.backends.storage_errors import classify_storage_error


def test_compat_client_config_disables_optional_checksums() -> None:
    pytest.importorskip("botocore")
    cfg = _compat_s3_client_config("virtual")
    assert cfg.signature_version == "s3v4"
    assert getattr(cfg, "request_checksum_calculation", "when_required") == "when_required"
    assert getattr(cfg, "response_checksum_validation", "when_required") == "when_required"


def test_classifies_not_implemented_header_error() -> None:
    classified = classify_storage_error(
        "An error occurred (NotImplemented) when calling the ListObjectsV2 operation: "
        "A header you provided implies functionality that is not implemented.",
    )
    assert classified.message_key == "probe_s3_incompatible"
    assert "path-style" in classified.message


def test_is_s3_not_implemented() -> None:
    class _S3Error(Exception):
        response = {
            "Error": {
                "Code": "NotImplemented",
                "Message": "A header you provided implies functionality that is not implemented.",
            },
            "ResponseMetadata": {"HTTPStatusCode": 501},
        }

    assert _is_s3_not_implemented(_S3Error()) is True


def test_list_objects_falls_back_to_v1() -> None:
    pytest.importorskip("botocore")
    from botocore.exceptions import ClientError

    backend = S3Backend.__new__(S3Backend)
    backend._config = S3Config(
        bucket="demo",
        access_key_id="AKIAIOSFODNN7EXAMPLE",
        secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    )
    client = MagicMock()
    client.list_objects_v2.side_effect = ClientError(
        {
            "Error": {
                "Code": "NotImplemented",
                "Message": "A header you provided implies functionality that is not implemented.",
            },
            "ResponseMetadata": {"HTTPStatusCode": 501},
        },
        "ListObjectsV2",
    )
    client.list_objects.return_value = {
        "Contents": [{"Key": "a.txt", "Size": 1}],
        "IsTruncated": False,
    }
    backend._client = client

    resp = backend._list_objects_page(Bucket="demo", Prefix="", Delimiter="/", MaxKeys=1000)
    assert resp["Contents"][0]["Key"] == "a.txt"
    client.list_objects.assert_called_once()


def test_custom_endpoint_defaults_to_path_style() -> None:
    cfg = S3Config.from_kwargs(
        bucket="demo",
        access_key_id="AKIAIOSFODNN7EXAMPLE",
        secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        endpoint_url="https://s3.example.com",
    )
    assert cfg.addressing_style == "path"
    assert cfg.signature_version == "s3v4"


def test_aws_without_endpoint_stays_virtual() -> None:
    cfg = S3Config.from_kwargs(
        bucket="demo",
        access_key_id="AKIAIOSFODNN7EXAMPLE",
        secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        region="us-east-1",
    )
    assert cfg.addressing_style == "virtual"


def test_list_falls_back_on_signature_mismatch() -> None:
    pytest.importorskip("botocore")
    from botocore.exceptions import ClientError

    backend = S3Backend.__new__(S3Backend)
    backend._config = S3Config(
        bucket="demo",
        access_key_id="AKIAIOSFODNN7EXAMPLE",
        secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    )
    backend._alt_client = None
    client = MagicMock()
    client.list_objects_v2.side_effect = ClientError(
        {
            "Error": {
                "Code": "SignatureDoesNotMatch",
                "Message": "The request signature we calculated does not match.",
            },
            "ResponseMetadata": {"HTTPStatusCode": 403},
        },
        "ListObjectsV2",
    )
    client.list_objects.return_value = {
        "Contents": [{"Key": "ok.txt", "Size": 2}],
        "IsTruncated": False,
    }
    backend._client = client
    resp = backend._list_objects_page(Bucket="demo", Prefix="", MaxKeys=1000)
    assert resp["Contents"][0]["Key"] == "ok.txt"


def test_get_object_falls_back_on_signature_mismatch() -> None:
    pytest.importorskip("botocore")
    from botocore.exceptions import ClientError

    from octop_harness.backends.s3_backend import _is_s3_signature_mismatch

    assert _is_s3_signature_mismatch(
        ClientError(
            {"Error": {"Code": "SignatureDoesNotMatch", "Message": "nope"}},
            "GetObject",
        )
    )
    backend = S3Backend.__new__(S3Backend)
    backend._config = S3Config(
        bucket="demo",
        access_key_id="AKIAIOSFODNN7EXAMPLE",
        secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    )
    backend._alt_client = None
    primary = MagicMock()
    primary.get_object.side_effect = ClientError(
        {
            "Error": {"Code": "SignatureDoesNotMatch", "Message": "nope"},
            "ResponseMetadata": {"HTTPStatusCode": 403},
        },
        "GetObject",
    )
    alt = MagicMock()
    alt.get_object.return_value = {"Body": MagicMock(read=lambda: b'{"content":"ok","encoding":"utf-8"}')}
    backend._client = primary
    backend._alt_client = alt
    raw = backend._get_object_bytes("foo.txt")
    assert raw == b'{"content":"ok","encoding":"utf-8"}'
    alt.get_object.assert_called_once()


def test_parse_body_accepts_raw_binary() -> None:
    from octop_harness.backends.cloud_storage_base import CloudStorageBackend

    data = CloudStorageBackend._parse_body(b"\x00\xff\xfe")
    assert data["encoding"] == "base64"


def test_classifies_signature_mismatch_separately() -> None:
    classified = classify_storage_error(
        "An error occurred (SignatureDoesNotMatch) when calling the ListObjectsV2 operation: "
        "The request signature we calculated does not match the signature you provided.",
    )
    assert classified.message_key == "probe_signature_mismatch"
    assert "access key" not in classified.message.lower()
