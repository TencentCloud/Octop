"""Tencent Cloud COS backend (uses the official ``cos-python-sdk-v5``).

Inherits all ``BackendProtocol`` methods from
:class:`~octop_harness.backends.cloud_storage_base.CloudStorageBackend`;
only the SDK-specific primitives are implemented here.

We deliberately use the official Tencent Cloud SDK rather than boto3 to
avoid the v4-signature / addressing-style pitfalls that affect S3-compatible
client libraries (COS *requires* virtual-hosted style which
``deepagents-backends.S3Backend`` v0.2.0 does not set).

Storage layout
--------------
Every virtual file at ``/foo/bar.txt`` maps to a COS object whose key is
``<prefix>foo/bar.txt``. The object body is JSON matching deepagents'
``FileData`` shape::

    {"content": "...", "encoding": "utf-8",
     "created_at": "...", "modified_at": "..."}

Behavior contract (per BackendProtocol)
---------------------------------------
- All methods return their respective Result dataclass with ``error`` set
  on failure; **never raise** for expected conditions (file-not-found,
  duplicate-write, etc.).
- ``write`` is create-only — refuses to overwrite an existing key.
- ``edit`` enforces unique-match unless ``replace_all=True``.
- ``glob`` returns an empty list on no matches (not an error).
- For an external-storage backend, ``files_update`` is omitted (the
  field was deprecated in deepagents 0.5).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from deepagents.backends.protocol import FileData, FileInfo

from octop_harness.backends.cloud_storage_base import CloudStorageBackend

if TYPE_CHECKING:
    from qcloud_cos import CosS3Client

logger = logging.getLogger(__name__)


@dataclass
class CosConfig:
    """Connection parameters for Tencent Cloud COS.

    Attributes:
        bucket: Bucket name **including the APPID suffix** (e.g.
            ``"my-bucket-1250000000"``). COS bucket names always carry the
            owning account's APPID.
        region: Region identifier (e.g. ``"ap-guangzhou"``,
            ``"ap-beijing"``, ``"na-siliconvalley"``).
        secret_id: Tencent Cloud SecretId.
        secret_key: Tencent Cloud SecretKey.
        prefix: Key prefix applied to every virtual path. Empty by default;
            useful when sharing a bucket between agents.
        token: Optional STS temporary credentials token.
        scheme: ``"https"`` (default) or ``"http"``. Production should
            always use https.
        timeout: Per-request timeout in seconds. ``None`` lets the SDK
            choose its default.
        endpoint: Optional custom endpoint (defaults to the standard
            ``cos.<region>.myqcloud.com``).
    """

    bucket: str
    region: str
    secret_id: str
    secret_key: str
    prefix: str = ""
    token: str | None = None
    scheme: str = "https"
    timeout: int | None = 30
    endpoint: str | None = None
    extra_config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.bucket:
            raise ValueError("CosConfig.bucket is required")
        if not self.region:
            raise ValueError("CosConfig.region is required")
        if not self.secret_id or not self.secret_key:
            raise ValueError("CosConfig.secret_id / secret_key are required")
        object.__setattr__(self, "prefix", self.prefix.strip("/"))


class CosBackend(CloudStorageBackend):
    """Tencent Cloud COS-backed virtual filesystem.

    Uses the official ``cos-python-sdk-v5`` SDK. All ``BackendProtocol``
    methods are inherited from :class:`CloudStorageBackend`; only COS SDK
    calls are implemented here.
    """

    def __init__(self, config: CosConfig, *, client: CosS3Client | None = None) -> None:
        self._config = config
        self._client: CosS3Client = client if client is not None else self._build_client(config)

    @property
    def _prefix(self) -> str:
        return self._config.prefix

    def _storage_error_types(self) -> tuple[type[BaseException], ...]:
        from qcloud_cos.cos_exception import CosServiceError

        return (*super()._storage_error_types(), CosServiceError)

    @staticmethod
    def _build_client(config: CosConfig) -> CosS3Client:
        from qcloud_cos import CosConfig as _CosConfig
        from qcloud_cos import CosS3Client as _CosS3Client

        kwargs: dict[str, Any] = {
            "Region": config.region,
            "SecretId": config.secret_id,
            "SecretKey": config.secret_key,
            "Scheme": config.scheme,
        }
        if config.token:
            kwargs["Token"] = config.token
        if config.timeout is not None:
            kwargs["Timeout"] = config.timeout
        if config.endpoint:
            kwargs["Endpoint"] = config.endpoint
        kwargs.update(config.extra_config)
        return _CosS3Client(_CosConfig(**kwargs))

    # ------------------------------------------------------------------
    # SDK primitives
    # ------------------------------------------------------------------

    def _get_file_data(self, path: str) -> FileData | None:
        key = self._key(path)
        from qcloud_cos.cos_exception import CosServiceError

        try:
            resp = self._client.get_object(Bucket=self._config.bucket, Key=key)
        except CosServiceError as exc:
            if exc.get_status_code() == 404 or exc.get_error_code() in {
                "NoSuchKey",
                "NoSuchObject",
            }:
                return None
            raise

        body = resp["Body"].get_raw_stream().read()
        return self._parse_body(body)

    def _put_file_data(self, path: str, file_data: FileData) -> None:
        self._client.put_object(
            Bucket=self._config.bucket,
            Key=self._key(path),
            Body=self._encode_file_data(file_data),
        )

    def _put_dir_marker(self, virtual_dir: str) -> None:
        self._client.put_object(
            Bucket=self._config.bucket,
            Key=self._prefix_key(virtual_dir),
            Body=b"",
        )

    def _ls_entries(self, path: str) -> list[FileInfo]:
        prefix_key = self._key(path)
        if prefix_key and not prefix_key.endswith("/"):
            prefix_key = prefix_key + "/"

        entries: list[FileInfo] = []
        marker = ""
        while True:
            resp = self._client.list_objects(
                Bucket=self._config.bucket,
                Prefix=prefix_key,
                Delimiter="/",
                Marker=marker,
                MaxKeys=1000,
            )
            for cp in resp.get("CommonPrefixes") or []:
                key = cp["Prefix"] if isinstance(cp, dict) else cp
                vp = self._virtual_path(key.rstrip("/"))
                entries.append({"path": vp, "is_dir": True})
            for obj in resp.get("Contents") or []:
                key = obj["Key"] if isinstance(obj, dict) else obj
                if key == prefix_key:
                    continue
                vp = self._virtual_path(key)
                size = int(obj.get("Size", 0)) if isinstance(obj, dict) else 0
                last_mod = obj.get("LastModified") if isinstance(obj, dict) else None
                info: FileInfo = {"path": vp, "is_dir": False, "size": size}
                if last_mod:
                    info["modified_at"] = str(last_mod)
                entries.append(info)
            if str(resp.get("IsTruncated", "false")).lower() != "true":
                break
            marker = resp.get("NextMarker") or ""
            if not marker:
                break

        entries.sort(key=lambda e: e["path"])
        return entries

    def _collect_recursive(self, path: str) -> dict[str, FileData]:
        from qcloud_cos.cos_exception import CosServiceError

        prefix_key = self._key(path)
        if prefix_key and not prefix_key.endswith("/") and path != "/":
            prefix_key = prefix_key + "/"

        files: dict[str, FileData] = {}
        marker = ""
        while True:
            resp = self._client.list_objects(
                Bucket=self._config.bucket,
                Prefix=prefix_key,
                Marker=marker,
                MaxKeys=1000,
            )
            for obj in resp.get("Contents") or []:
                key = obj["Key"] if isinstance(obj, dict) else obj
                if key.endswith("/"):
                    continue
                vp = self._virtual_path(key)
                try:
                    fd = self._get_file_data(vp)
                except CosServiceError:
                    continue
                if fd is not None:
                    files[vp] = fd
            if str(resp.get("IsTruncated", "false")).lower() != "true":
                break
            marker = resp.get("NextMarker") or ""
            if not marker:
                break
        return files

    def _iter_prefix_object_keys(self, path: str) -> Any:
        prefix_key = self._prefix_key(path)
        marker = ""
        while True:
            resp = self._client.list_objects(
                Bucket=self._config.bucket,
                Prefix=prefix_key,
                Marker=marker,
                MaxKeys=1000,
            )
            for obj in resp.get("Contents") or []:
                yield obj["Key"] if isinstance(obj, dict) else obj
            if str(resp.get("IsTruncated", "false")).lower() != "true":
                break
            marker = resp.get("NextMarker") or ""
            if not marker:
                break

    def _prefix_has_objects(self, path: str) -> bool:
        resp = self._client.list_objects(
            Bucket=self._config.bucket,
            Prefix=self._prefix_key(path),
            MaxKeys=1,
        )
        return bool(resp.get("Contents"))

    def _copy_object(self, src: str, dest: str) -> None:
        self._client.copy_object(
            Bucket=self._config.bucket,
            Key=self._key(dest),
            CopySource={
                "Bucket": self._config.bucket,
                "Key": self._key(src),
                "Region": self._config.region,
            },
        )

    def delete_object(self, path: str) -> None:
        """Delete the COS object backing ``path`` (probe / admin cleanup)."""
        self._client.delete_object(Bucket=self._config.bucket, Key=self._key(path))

    def delete_prefix(self, path: str) -> int:
        """Delete every object under ``path``. Returns the number of keys removed."""
        deleted = 0
        for key in self._iter_prefix_object_keys(path):
            self._client.delete_object(Bucket=self._config.bucket, Key=key)
            deleted += 1
        return deleted


__all__ = ["CosBackend", "CosConfig"]
