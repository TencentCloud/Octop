"""Unit tests for S3/COS remote backup provider (mocked boto3 client)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError

from octop.infra.backup.remote import get_provider
from octop.infra.backup.remote.providers.s3 import S3BackupProvider
from octop.infra.errors import ErrorCode, OctopError


class _FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.head_bucket_calls = 0
        self.fail_head: ClientError | None = None

    def head_bucket(self, *, Bucket: str) -> dict[str, Any]:
        self.head_bucket_calls += 1
        if self.fail_head is not None:
            raise self.fail_head
        return {}

    def upload_file(self, Filename: str, Bucket: str, Key: str) -> None:
        self.objects[Key] = Path(Filename).read_bytes()

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        data = self.objects.get(Key)
        if data is None:
            raise ClientError(
                {
                    "Error": {"Code": "404", "Message": "Not Found"},
                    "ResponseMetadata": {"HTTPStatusCode": 404},
                },
                "HeadObject",
            )
        return {"ContentLength": len(data)}

    def list_objects_v2(self, **kwargs: Any) -> dict[str, Any]:
        prefix = str(kwargs.get("Prefix") or "")
        contents = []
        for key, body in sorted(self.objects.items()):
            if prefix and not key.startswith(prefix):
                continue
            rest = key[len(prefix) :] if prefix else key
            if "/" in rest:
                continue
            contents.append(
                {
                    "Key": key,
                    "Size": len(body),
                    "LastModified": datetime(2026, 1, 2, tzinfo=UTC),
                }
            )
        return {"Contents": contents, "IsTruncated": False}

    def download_file(self, Bucket: str, Key: str, Filename: str) -> None:
        data = self.objects.get(Key)
        if data is None:
            raise ClientError(
                {
                    "Error": {"Code": "NoSuchKey", "Message": "missing"},
                    "ResponseMetadata": {"HTTPStatusCode": 404},
                },
                "GetObject",
            )
        Path(Filename).write_bytes(data)

    def delete_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        self.objects.pop(Key, None)
        return {}


def _client_error(*, code: str, status: int) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": code},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        "Op",
    )


def test_from_settings_requires_bucket() -> None:
    with pytest.raises(OctopError) as exc_info:
        S3BackupProvider.from_settings(
            bucket="",
            access_key="ak",
            secret_key="sk",
            base_dir="Apps",
            kind="cos",
        )
    assert exc_info.value.code == ErrorCode.SLASH_BAD_ARGS


def test_cos_derives_endpoint_from_region() -> None:
    provider = S3BackupProvider.from_settings(
        bucket="b-125",
        access_key="ak",
        secret_key="sk",
        region="ap-shanghai",
        endpoint="",
        base_dir="Apps",
        kind="cos",
    )
    assert provider._settings.endpoint_url == "https://cos.ap-shanghai.myqcloud.com"
    assert provider._settings.label == "COS"


def test_object_key_joins_base_dir() -> None:
    provider = S3BackupProvider.from_settings(
        bucket="b-125",
        access_key="ak",
        secret_key="sk",
        region="ap-shanghai",
        endpoint="cos.ap-shanghai.myqcloud.com",
        base_dir="Apps",
        kind="cos",
    )
    assert provider._object_key("octop-auto-backup-20260101T000000Z.tar.gz") == (
        "Apps/octop-auto-backup-20260101T000000Z.tar.gz"
    )


def test_cos_and_s3_registered() -> None:
    cos = get_provider(
        "cos",
        bucket="b",
        access_key="ak",
        secret_key="sk",
        region="ap-guangzhou",
        base_dir="Apps",
    )
    s3 = get_provider(
        "s3",
        bucket="b",
        access_key="ak",
        secret_key="sk",
        base_dir="",
    )
    assert isinstance(cos, S3BackupProvider)
    assert isinstance(s3, S3BackupProvider)
    assert cos._settings.label == "COS"
    assert s3._settings.label == "S3"


@pytest.mark.asyncio
async def test_put_list_get_delete_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeS3Client()
    provider = S3BackupProvider.from_settings(
        bucket="b-125",
        access_key="ak",
        secret_key="sk",
        region="ap-shanghai",
        endpoint="https://cos.ap-shanghai.myqcloud.com",
        base_dir="Apps",
        kind="cos",
    )
    monkeypatch.setattr(provider, "_client", lambda: fake)

    local = tmp_path / "octop-auto-backup-20260101T000000Z.tar.gz"
    local.write_bytes(b"abc123")
    result = await provider.put(local, local.name)
    assert result.status == "remote_ok"
    assert "Apps/octop-auto-backup-20260101T000000Z.tar.gz" in fake.objects

    listed = await provider.list()
    assert [item.name for item in listed] == [local.name]
    assert listed[0].size == 6

    dest = tmp_path / "downloaded.tar.gz"
    await provider.get(local.name, dest)
    assert dest.read_bytes() == b"abc123"

    await provider.delete(local.name)
    assert fake.objects == {}


@pytest.mark.asyncio
async def test_test_maps_access_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeS3Client()
    fake.fail_head = _client_error(code="AccessDenied", status=403)
    provider = S3BackupProvider.from_settings(
        bucket="b",
        access_key="ak",
        secret_key="sk",
        kind="cos",
    )
    monkeypatch.setattr(provider, "_client", lambda: fake)
    with pytest.raises(OctopError) as exc_info:
        await provider.test()
    assert exc_info.value.code == ErrorCode.NETWORK_ERROR
    assert "authentication" in str(exc_info.value).lower()
