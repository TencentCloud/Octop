"""Alibaba Cloud OSS backend (uses the official ``oss2`` SDK).

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
    from oss2 import Bucket as OssBucket

logger = logging.getLogger(__name__)


@dataclass
class OssConfig:
    """Connection parameters for Alibaba Cloud OSS.

    Attributes:
        bucket: Bucket name (e.g. ``"my-bucket"``).
        endpoint: OSS endpoint (e.g. ``"oss-cn-hangzhou.aliyuncs.com"``).
            Scheme is optional; ``https`` is used by default.
        access_key_id: AccessKey ID.
        access_key_secret: AccessKey secret.
        prefix: Key prefix applied to every virtual path. Empty by default.
        connect_timeout: Socket connect timeout in seconds. Default 30.
    """

    bucket: str
    endpoint: str
    access_key_id: str
    access_key_secret: str
    prefix: str = ""
    connect_timeout: int = 30
    extra_kwargs: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.bucket:
            raise ValueError("OssConfig.bucket is required")
        if not self.endpoint:
            raise ValueError("OssConfig.endpoint is required")
        if not self.access_key_id or not self.access_key_secret:
            raise ValueError("OssConfig.access_key_id / access_key_secret are required")
        object.__setattr__(self, "prefix", self.prefix.strip("/"))

    @property
    def endpoint_url(self) -> str:
        ep = self.endpoint
        if "://" not in ep:
            ep = f"https://{ep}"
        return ep


class OssBackend(CloudStorageBackend):
    """Alibaba Cloud OSS-backed virtual filesystem.

    Uses the official ``oss2`` SDK. All ``BackendProtocol`` methods are
    inherited from :class:`CloudStorageBackend`; only OSS SDK calls are here.
    """

    def __init__(self, config: OssConfig, *, bucket: OssBucket | None = None) -> None:
        self._config = config
        self._bucket = bucket if bucket is not None else self._build_bucket(config)

    @property
    def _prefix(self) -> str:
        return self._config.prefix

    def _storage_error_types(self) -> tuple[type[BaseException], ...]:
        import oss2 as _oss2

        return (*super()._storage_error_types(), _oss2.exceptions.ServerError)

    @staticmethod
    def _build_bucket(config: OssConfig) -> OssBucket:
        try:
            import oss2 as _oss2
        except ImportError as exc:
            raise ImportError("OSS backend requires 'oss2'. Install with: pip install oss2") from exc
        auth = _oss2.Auth(config.access_key_id, config.access_key_secret)
        return _oss2.Bucket(
            auth,
            config.endpoint_url,
            config.bucket,
            connect_timeout=config.connect_timeout,
            is_cname=False,
            **config.extra_kwargs,
        )

    # ------------------------------------------------------------------
    # SDK primitives
    # ------------------------------------------------------------------

    def _get_file_data(self, path: str) -> FileData | None:
        import oss2 as _oss2

        key = self._key(path)
        try:
            result = self._bucket.get_object(key)
        except _oss2.exceptions.NoSuchKey:
            return None
        except _oss2.exceptions.ServerError as exc:
            if exc.status == 404:
                return None
            raise
        return self._parse_body(result.read())

    def _put_file_data(self, path: str, file_data: FileData) -> None:
        self._bucket.put_object(self._key(path), self._encode_file_data(file_data))

    def _put_dir_marker(self, virtual_dir: str) -> None:
        self._bucket.put_object(self._prefix_key(virtual_dir), b"")

    def _ls_entries(self, path: str) -> list[FileInfo]:
        import oss2 as _oss2

        prefix_key = self._key(path)
        if prefix_key and not prefix_key.endswith("/"):
            prefix_key += "/"

        entries: list[FileInfo] = []
        for obj in _oss2.ObjectIterator(self._bucket, prefix=prefix_key, delimiter="/"):
            if obj.is_prefix():
                vp = self._virtual_path(obj.key.rstrip("/"))
                entries.append({"path": vp, "is_dir": True})
            else:
                if obj.key == prefix_key:
                    continue
                vp = self._virtual_path(obj.key)
                info: FileInfo = {"path": vp, "is_dir": False, "size": obj.size}
                if obj.last_modified:
                    info["modified_at"] = str(obj.last_modified)
                entries.append(info)

        entries.sort(key=lambda e: e["path"])
        return entries

    def _collect_recursive(self, path: str) -> dict[str, FileData]:
        import oss2 as _oss2

        prefix_key = self._key(path)
        if prefix_key and not prefix_key.endswith("/") and path != "/":
            prefix_key += "/"

        files: dict[str, FileData] = {}
        for obj in _oss2.ObjectIterator(self._bucket, prefix=prefix_key):
            if obj.is_prefix() or obj.key.endswith("/"):
                continue
            vp = self._virtual_path(obj.key)
            try:
                fd = self._get_file_data(vp)
            except _oss2.exceptions.ServerError:
                continue
            if fd is not None:
                files[vp] = fd
        return files

    def _iter_prefix_object_keys(self, path: str) -> Any:
        import oss2 as _oss2

        for obj in _oss2.ObjectIterator(self._bucket, prefix=self._prefix_key(path)):
            if not obj.is_prefix():
                yield obj.key

    def _prefix_has_objects(self, path: str) -> bool:
        result = self._bucket.list_objects(prefix=self._prefix_key(path), max_keys=1)
        return bool(result.object_list)

    def _copy_object(self, src: str, dest: str) -> None:
        self._bucket.copy_object(self._config.bucket, self._key(src), self._key(dest))

    def delete_object(self, path: str) -> None:
        self._bucket.delete_object(self._key(path))

    def delete_prefix(self, path: str) -> int:
        deleted = 0
        for key in self._iter_prefix_object_keys(path):
            self._bucket.delete_object(key)
            deleted += 1
        return deleted


__all__ = ["OssBackend", "OssConfig"]
