"""S3-compatible remote backup provider (AWS S3, Tencent COS, …) via boto3."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from octop.infra.backup.remote.registry import register_provider
from octop.infra.backup.remote.types import MirrorResult, RemoteObject
from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)

_DEFAULT_CONNECT_TIMEOUT_S = 10.0
_DEFAULT_READ_TIMEOUT_S = 120.0


@dataclass(frozen=True)
class S3Settings:
    bucket: str
    access_key: str
    secret_key: str
    region: str | None
    endpoint_url: str | None
    key_prefix: str
    label: str


class S3BackupProvider:
    """Upload/list/download/delete backup archives on an S3-compatible bucket."""

    def __init__(self, settings: S3Settings) -> None:
        self._settings = settings

    @classmethod
    def from_settings(
        cls,
        *,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str = "",
        endpoint: str = "",
        base_dir: str = "",
        kind: str = "s3",
    ) -> S3BackupProvider:
        bucket_name = (bucket or "").strip()
        if not bucket_name:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "bucket is required")
        if not (access_key or "").strip() or not (secret_key or "").strip():
            raise OctopError(
                ErrorCode.SLASH_BAD_ARGS,
                "access_key and secret_key are required",
            )
        raw_endpoint = (endpoint or "").strip()
        region_name = (region or "").strip() or None
        kind_key = (kind or "").strip().lower()
        # COS rows often omit endpoint and only store region; without an
        # explicit endpoint boto3 would talk to AWS S3 hostnames instead.
        if not raw_endpoint and kind_key == "cos" and region_name:
            raw_endpoint = f"cos.{region_name}.myqcloud.com"
        endpoint_url: str | None
        if not raw_endpoint:
            endpoint_url = None
        elif "://" in raw_endpoint:
            endpoint_url = raw_endpoint
        else:
            endpoint_url = f"https://{raw_endpoint}"
        # ``base_dir`` is an opaque key prefix from remote-backup resolve.
        prefix = (base_dir or "").strip().strip("/")
        label = "COS" if kind_key == "cos" else "S3"
        return cls(
            S3Settings(
                bucket=bucket_name,
                access_key=access_key.strip(),
                secret_key=secret_key.strip(),
                region=region_name,
                endpoint_url=endpoint_url,
                key_prefix=prefix,
                label=label,
            )
        )

    def _object_key(self, remote_name: str) -> str:
        name = (remote_name or "").replace("\\", "/").strip()
        if not name or "/" in name or name in {".", ".."} or name.endswith(".part"):
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "invalid remote archive name")
        if self._settings.key_prefix:
            return f"{self._settings.key_prefix}/{name}"
        return name

    def _list_prefix(self) -> str:
        if self._settings.key_prefix:
            return f"{self._settings.key_prefix}/"
        return ""

    def _client(self) -> Any:
        import boto3

        return boto3.client(
            "s3",
            endpoint_url=self._settings.endpoint_url,
            aws_access_key_id=self._settings.access_key,
            aws_secret_access_key=self._settings.secret_key,
            region_name=self._settings.region,
            config=Config(
                connect_timeout=_DEFAULT_CONNECT_TIMEOUT_S,
                read_timeout=_DEFAULT_READ_TIMEOUT_S,
                retries={"max_attempts": 3, "mode": "standard"},
                s3={
                    "addressing_style": "virtual",
                    "payload_signature_version": "s3v4",
                },
            ),
        )

    def _reason(self, text: str) -> str:
        cleaned = text
        secret = self._settings.secret_key
        if secret:
            cleaned = cleaned.replace(secret, "***")
        return cleaned

    def _map_client_error(self, *, op: str, exc: ClientError) -> OctopError:
        code = str(exc.response.get("Error", {}).get("Code") or "")
        status = int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") or 0)
        if code in {"404", "NoSuchBucket", "NoSuchKey", "NotFound"} or status == 404:
            reason = (
                f"{self._settings.label} {op} not found — check bucket/region/endpoint/base_dir"
            )
            return OctopError(
                ErrorCode.NOT_FOUND if op in {"download", "delete"} else ErrorCode.NETWORK_ERROR,
                self._reason(reason),
                details={"reason": self._reason(reason), "http_status": status or None},
            )
        if code in {
            "403",
            "AccessDenied",
            "InvalidAccessKeyId",
            "SignatureDoesNotMatch",
        } or status in {
            401,
            403,
        }:
            reason = (
                f"{self._settings.label} {op} authentication failed — "
                "check access_key and secret_key"
            )
            return OctopError(
                ErrorCode.NETWORK_ERROR,
                self._reason(reason),
                details={"reason": self._reason(reason), "http_status": status or None},
            )
        reason = f"{self._settings.label} {op} failed: {code or status or exc}"
        return OctopError(
            ErrorCode.NETWORK_ERROR,
            self._reason(reason),
            details={"reason": self._reason(reason), "http_status": status or None},
        )

    async def test(self) -> None:
        def _head() -> None:
            client = self._client()
            client.head_bucket(Bucket=self._settings.bucket)

        try:
            await asyncio.to_thread(_head)
        except ClientError as exc:
            raise self._map_client_error(op="connectivity", exc=exc) from exc
        except BotoCoreError as exc:
            reason = self._reason(f"{self._settings.label} connectivity failed: {exc}")
            raise OctopError(
                ErrorCode.NETWORK_ERROR,
                reason,
                details={"reason": reason},
            ) from exc

    async def put(self, local_path: Path, remote_name: str) -> MirrorResult:
        if not local_path.is_file():
            return MirrorResult(status="remote_failed", reason="local archive missing")
        size = local_path.stat().st_size
        key = self._object_key(remote_name)

        def _upload() -> int:
            client = self._client()
            client.upload_file(str(local_path), self._settings.bucket, key)
            head = client.head_object(Bucket=self._settings.bucket, Key=key)
            return int(head.get("ContentLength") or 0)

        try:
            remote_size = await asyncio.to_thread(_upload)
        except ClientError as exc:
            mapped = self._map_client_error(op="upload", exc=exc)
            return MirrorResult(status="remote_failed", reason=str(mapped))
        except BotoCoreError as exc:
            return MirrorResult(
                status="remote_failed",
                reason=self._reason(f"{self._settings.label} upload failed: {exc}"),
            )
        except Exception as exc:  # noqa: BLE001 — map unexpected I/O into mirror status
            logger.exception("%s put failed", self._settings.label.lower())
            return MirrorResult(
                status="remote_failed",
                reason=self._reason(f"{self._settings.label} upload failed: {exc}"),
            )
        if remote_size != size:
            return MirrorResult(
                status="remote_failed",
                reason=f"remote size {remote_size} != local size {size}",
            )
        return MirrorResult(status="remote_ok", reason="put verified")

    async def list(self) -> list[RemoteObject]:
        prefix = self._list_prefix()

        def _list() -> list[RemoteObject]:
            client = self._client()
            items: list[RemoteObject] = []
            token: str | None = None
            while True:
                kwargs: dict[str, Any] = {
                    "Bucket": self._settings.bucket,
                    "Prefix": prefix,
                    "Delimiter": "/",
                }
                if token:
                    kwargs["ContinuationToken"] = token
                page = client.list_objects_v2(**kwargs)
                for obj in page.get("Contents") or []:
                    key = str(obj.get("Key") or "")
                    if not key or key.endswith("/") or key.endswith(".part"):
                        continue
                    name = Path(key).name
                    if not name:
                        continue
                    # Only direct children of the prefix (Delimiter="/" already
                    # excludes nested keys from Contents in normal S3).
                    if prefix and not key.startswith(prefix):
                        continue
                    if prefix and "/" in key[len(prefix) :]:
                        continue
                    modified = None
                    last_modified = obj.get("LastModified")
                    if last_modified is not None:
                        try:
                            modified = last_modified.isoformat()
                        except Exception:  # noqa: BLE001 — best-effort display field
                            modified = str(last_modified)
                    items.append(
                        RemoteObject(
                            name=name,
                            size=int(obj.get("Size") or 0),
                            modified_at=modified,
                        )
                    )
                if not page.get("IsTruncated"):
                    break
                token = page.get("NextContinuationToken")
                if not token:
                    break
            return items

        try:
            return await asyncio.to_thread(_list)
        except ClientError as exc:
            raise self._map_client_error(op="list", exc=exc) from exc
        except BotoCoreError as exc:
            reason = self._reason(f"{self._settings.label} list failed: {exc}")
            raise OctopError(
                ErrorCode.NETWORK_ERROR,
                reason,
                details={"reason": reason},
            ) from exc

    async def get(self, remote_name: str, dest: Path) -> None:
        key = self._object_key(remote_name)

        def _download() -> None:
            dest.parent.mkdir(parents=True, exist_ok=True)
            client = self._client()
            client.download_file(self._settings.bucket, key, str(dest))

        try:
            await asyncio.to_thread(_download)
        except ClientError as exc:
            raise self._map_client_error(op="download", exc=exc) from exc
        except BotoCoreError as exc:
            reason = self._reason(f"{self._settings.label} download failed: {exc}")
            raise OctopError(
                ErrorCode.NETWORK_ERROR,
                reason,
                details={"reason": reason},
            ) from exc

    async def delete(self, remote_name: str) -> None:
        key = self._object_key(remote_name)

        def _delete() -> None:
            client = self._client()
            client.delete_object(Bucket=self._settings.bucket, Key=key)

        try:
            await asyncio.to_thread(_delete)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code") or "")
            status = int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") or 0)
            if code in {"404", "NoSuchKey", "NotFound"} or status == 404:
                return
            raise self._map_client_error(op="delete", exc=exc) from exc
        except BotoCoreError as exc:
            reason = self._reason(f"{self._settings.label} delete failed: {exc}")
            raise OctopError(
                ErrorCode.NETWORK_ERROR,
                reason,
                details={"reason": reason},
            ) from exc


def _factory(storage_kind: str, **kwargs: object) -> S3BackupProvider:
    return S3BackupProvider.from_settings(
        bucket=str(kwargs.get("bucket") or ""),
        access_key=str(kwargs.get("access_key") or ""),
        secret_key=str(kwargs.get("secret_key") or ""),
        region=str(kwargs.get("region") or ""),
        endpoint=str(kwargs.get("endpoint") or ""),
        base_dir=str(kwargs.get("base_dir") or ""),
        kind=storage_kind,
    )


register_provider("s3", lambda **kwargs: _factory("s3", **kwargs))
register_provider("cos", lambda **kwargs: _factory("cos", **kwargs))
