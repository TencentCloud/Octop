"""Huawei Cloud OBS backend (uses the official ``esdk-obs-python`` SDK).

Inherits all ``BackendProtocol`` methods from
:class:`~octop_harness.backends.cloud_storage_base.CloudStorageBackend`;
only the SDK-specific primitives are implemented here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from deepagents.backends.protocol import FileData, FileInfo

from octop_harness.backends.cloud_storage_base import CloudStorageBackend

if TYPE_CHECKING:
    from obs import ObsClient

logger = logging.getLogger(__name__)

# OBS HTTP status codes that indicate "object not found".
_OBS_NOT_FOUND_CODES = {404, 405}


@dataclass
class ObsConfig:
    """Connection parameters for Huawei Cloud OBS.

    Attributes:
        bucket: Bucket name (e.g. ``"my-bucket"``).
        endpoint: OBS endpoint (e.g. ``"obs.cn-north-4.myhuaweicloud.com"``).
            Scheme is optional; ``https`` is used by default.
        access_key_id: AK (Access Key).
        secret_access_key: SK (Secret Key).
        prefix: Key prefix applied to every virtual path. Empty by default.
        security_token: Optional STS temporary security token.
        connect_timeout: Connection timeout in seconds. Default 30.
        socket_timeout: Socket timeout in seconds. Default 60.
    """

    bucket: str
    endpoint: str
    access_key_id: str
    secret_access_key: str
    prefix: str = ""
    security_token: str | None = None
    connect_timeout: int = 30
    socket_timeout: int = 60
    extra_kwargs: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.bucket:
            raise ValueError("ObsConfig.bucket is required")
        if not self.endpoint:
            raise ValueError("ObsConfig.endpoint is required")
        if not self.access_key_id or not self.secret_access_key:
            raise ValueError("ObsConfig.access_key_id / secret_access_key are required")
        object.__setattr__(self, "prefix", self.prefix.strip("/"))

    @property
    def endpoint_url(self) -> str:
        ep = self.endpoint
        if "://" not in ep:
            ep = f"https://{ep}"
        return ep


class ObsBackend(CloudStorageBackend):
    """Huawei Cloud OBS-backed virtual filesystem.

    Uses the official ``esdk-obs-python`` SDK. All ``BackendProtocol`` methods
    are inherited from :class:`CloudStorageBackend`; only OBS SDK calls are here.
    """

    def __init__(self, config: ObsConfig, *, client: ObsClient | None = None) -> None:
        self._config = config
        self._client: ObsClient = client if client is not None else self._build_client(config)

    @property
    def _prefix(self) -> str:
        return self._config.prefix

    @staticmethod
    def _build_client(config: ObsConfig) -> ObsClient:
        try:
            from obs import ObsClient as _ObsClient
        except ImportError as exc:
            raise ImportError(
                "OBS backend requires 'esdk-obs-python'. Install with: pip install esdk-obs-python"
            ) from exc
        kwargs: dict[str, Any] = {
            "access_key_id": config.access_key_id,
            "secret_access_key": config.secret_access_key,
            "server": config.endpoint_url,
            "timeout": (config.connect_timeout, config.socket_timeout),
        }
        if config.security_token:
            kwargs["security_token"] = config.security_token
        kwargs.update(config.extra_kwargs)
        return _ObsClient(**kwargs)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_resp(self, resp: Any, operation: str) -> None:
        """Raise RuntimeError when the OBS response indicates failure."""
        if resp.status >= 300:
            raise RuntimeError(
                f"OBS {operation} failed: status={resp.status} "
                f"code={getattr(resp, 'errorCode', '')} "
                f"message={getattr(resp, 'errorMessage', '')}"
            )

    def _is_not_found(self, resp: Any) -> bool:
        return resp.status in _OBS_NOT_FOUND_CODES

    # ------------------------------------------------------------------
    # SDK primitives
    # ------------------------------------------------------------------

    def _get_file_data(self, path: str) -> FileData | None:
        resp = self._client.getObject(
            bucketName=self._config.bucket,
            objectKey=self._key(path),
            loadStreamInMemory=True,
        )
        if self._is_not_found(resp):
            return None
        self._check_resp(resp, "getObject")
        return self._parse_body(resp.body.buffer)

    def _put_file_data(self, path: str, file_data: FileData) -> None:
        resp = self._client.putContent(
            bucketName=self._config.bucket,
            objectKey=self._key(path),
            content=self._encode_file_data(file_data),
        )
        self._check_resp(resp, "putContent")

    def _put_dir_marker(self, virtual_dir: str) -> None:
        resp = self._client.putContent(
            bucketName=self._config.bucket,
            objectKey=self._prefix_key(virtual_dir),
            content=b"",
        )
        self._check_resp(resp, "putContent")

    def _ls_entries(self, path: str) -> list[FileInfo]:
        prefix_key = self._key(path)
        if prefix_key and not prefix_key.endswith("/"):
            prefix_key += "/"

        entries: list[FileInfo] = []
        marker = ""
        while True:
            resp = self._client.listObjects(
                bucketName=self._config.bucket,
                prefix=prefix_key,
                delimiter="/",
                marker=marker,
                max_keys=1000,
            )
            self._check_resp(resp, "listObjects")
            body = resp.body

            for cp in body.commonPrefixs or []:
                vp = self._virtual_path(cp.prefix.rstrip("/"))
                entries.append({"path": vp, "is_dir": True})

            for obj in body.contents or []:
                if obj.key == prefix_key:
                    continue
                vp = self._virtual_path(obj.key)
                info: FileInfo = {"path": vp, "is_dir": False, "size": obj.size or 0}
                if obj.lastModified:
                    info["modified_at"] = str(obj.lastModified)
                entries.append(info)

            if not body.is_truncated:
                break
            marker = body.next_marker or ""
            if not marker:
                break

        entries.sort(key=lambda e: e["path"])
        return entries

    def _collect_recursive(self, path: str) -> dict[str, FileData]:
        prefix_key = self._key(path)
        if prefix_key and not prefix_key.endswith("/") and path != "/":
            prefix_key += "/"

        files: dict[str, FileData] = {}
        marker = ""
        while True:
            resp = self._client.listObjects(
                bucketName=self._config.bucket,
                prefix=prefix_key,
                marker=marker,
                max_keys=1000,
            )
            self._check_resp(resp, "listObjects")
            body = resp.body
            for obj in body.contents or []:
                if obj.key.endswith("/"):
                    continue
                vp = self._virtual_path(obj.key)
                try:
                    fd = self._get_file_data(vp)
                except RuntimeError:
                    continue
                if fd is not None:
                    files[vp] = fd
            if not body.is_truncated:
                break
            marker = body.next_marker or ""
            if not marker:
                break
        return files

    def _iter_prefix_object_keys(self, path: str) -> Any:
        prefix_key = self._prefix_key(path)
        marker = ""
        while True:
            resp = self._client.listObjects(
                bucketName=self._config.bucket,
                prefix=prefix_key,
                marker=marker,
                max_keys=1000,
            )
            self._check_resp(resp, "listObjects")
            for obj in resp.body.contents or []:
                yield obj.key
            if not resp.body.is_truncated:
                break
            marker = resp.body.next_marker or ""
            if not marker:
                break

    def _prefix_has_objects(self, path: str) -> bool:
        resp = self._client.listObjects(
            bucketName=self._config.bucket,
            prefix=self._prefix_key(path),
            max_keys=1,
        )
        return bool(resp.body.contents)

    def _copy_object(self, src: str, dest: str) -> None:
        resp = self._client.copyObject(
            sourceBucketName=self._config.bucket,
            sourceObjectKey=self._key(src),
            destBucketName=self._config.bucket,
            destObjectKey=self._key(dest),
        )
        self._check_resp(resp, "copyObject")

    def delete_object(self, path: str) -> None:
        resp = self._client.deleteObject(bucketName=self._config.bucket, objectKey=self._key(path))
        self._check_resp(resp, "deleteObject")

    def delete_prefix(self, path: str) -> int:
        deleted = 0
        for key in self._iter_prefix_object_keys(path):
            resp = self._client.deleteObject(bucketName=self._config.bucket, objectKey=key)
            self._check_resp(resp, "deleteObject")
            deleted += 1
        return deleted


__all__ = ["ObsBackend", "ObsConfig"]
