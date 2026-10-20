"""S3-compatible backend (boto3) — covers AWS S3, MinIO, and custom stores.

This module also provides :func:`cos_spec_to_s3_compat` as a fallback spec
converter for Tencent Cloud COS when the native ``cos-python-sdk-v5`` is
unavailable.

Inherits all ``BackendProtocol`` methods from
:class:`~octop_harness.backends.cloud_storage_base.CloudStorageBackend`;
only the boto3 SDK calls are implemented here.

Storage layout
--------------
Every virtual file at ``/foo/bar.txt`` maps to an S3 object whose key is
``<prefix>foo/bar.txt``. The object body is JSON matching deepagents'
``FileData`` shape::

    {"content": "...", "encoding": "utf-8",
     "created_at": "...", "modified_at": "..."}

Compatibility notes
-------------------
- Uses SigV4 by default (``signature_version="s3v4"``). ListObjectsV2 on
  S3-compatible stores often rejects SigV2 with ``SignatureDoesNotMatch``
  even when Put/Get (the probe) succeed.
- Custom ``endpoint_url`` defaults to path-style addressing; AWS (no
  custom endpoint) stays virtual-hosted. Optional CRC32 checksum headers
  from botocore 1.36+ are disabled.
- Pagination prefers ``list_objects_v2`` and falls back to ``list_objects``,
  then to the other signature version, when the store returns
  ``NotImplemented`` or ``SignatureDoesNotMatch``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, cast

from deepagents.backends.protocol import FileData, FileInfo

from octop_harness.backends.cloud_storage_base import CloudStorageBackend

logger = logging.getLogger(__name__)

# Community / Terraform / AWS-CLI spellings for path-style addressing.
_PATH_STYLE_ALIASES: tuple[str, ...] = (
    "s3_force_path_style",
    "force_path_style",
    "path_style",
)


def normalize_s3_spec_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Translate path-style aliases and consume them so constructors never see them.

    An explicit ``addressing_style`` always wins. The first present alias decides
    the fallback (``true`` → ``"path"``, ``false`` → ``"virtual"``).
    """
    out = dict(kwargs)
    requested_path: bool | None = None
    for alias in _PATH_STYLE_ALIASES:
        if alias not in out:
            continue
        value = out.pop(alias)
        if requested_path is None:
            requested_path = bool(value)
    if requested_path is not None and "addressing_style" not in out:
        out["addressing_style"] = "path" if requested_path else "virtual"
    return out


def _compat_s3_client_config(
    addressing_style: str,
    *,
    signature_version: str = "s3v4",
) -> Any:
    """boto3 client config that S3-compatible stores (MinIO, Ceph, COS, …) accept.

    botocore 1.36+ defaults to optional CRC32 checksum headers. Compatible
    endpoints often answer ``NotImplemented``: "A header you provided implies
    functionality that is not implemented."
    """
    import botocore.config

    kwargs: dict[str, Any] = {
        "signature_version": signature_version,
        "s3": {"addressing_style": addressing_style},
        "request_checksum_calculation": "when_required",
        "response_checksum_validation": "when_required",
    }
    try:
        return botocore.config.Config(**kwargs)
    except TypeError:
        kwargs.pop("request_checksum_calculation", None)
        kwargs.pop("response_checksum_validation", None)
        return botocore.config.Config(**kwargs)


def _is_s3_signature_mismatch(exc: BaseException) -> bool:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        code = str((response.get("Error") or {}).get("Code") or "")
        if code in {"SignatureDoesNotMatch", "InvalidRequest", "AuthorizationHeaderMalformed"}:
            return True
    text = str(exc)
    return "SignatureDoesNotMatch" in text or "signature we calculated" in text.lower()


def _list_v1_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    v1 = {key: value for key, value in kwargs.items() if key != "ContinuationToken"}
    token = kwargs.get("ContinuationToken")
    if token:
        v1["Marker"] = token
    return v1


def _normalize_list_v1(resp: dict[str, Any]) -> dict[str, Any]:
    if resp.get("IsTruncated") and not resp.get("NextContinuationToken"):
        marker = resp.get("NextMarker")
        if not marker:
            contents = resp.get("Contents") or []
            last = contents[-1] if contents else None
            marker = last.get("Key") if isinstance(last, dict) else None
        if marker:
            resp = dict(resp)
            resp["NextContinuationToken"] = marker
    return resp


def _is_s3_not_implemented(exc: BaseException) -> bool:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        error = response.get("Error") or {}
        code = str(error.get("Code") or "")
        message = str(error.get("Message") or "")
        status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in {"NotImplemented", "501"} or status == 501:
            return True
        if "not implemented" in message.lower():
            return True
    return "not implemented" in str(exc).lower()


@dataclass
class S3Config:
    """Connection parameters for an S3-compatible object store.

    Field names intentionally match the keys emitted by
    ``octop.infra.backend.adapter`` so that
    ``S3Backend(S3Config(**spec_kwargs))`` works directly.

    Attributes:
        bucket: Bucket name.
        access_key_id: Access key ID.
        secret_access_key: Secret access key.
        region: Region identifier (e.g. ``"us-east-1"``).
        endpoint_url: Custom endpoint URL including scheme.
        prefix: Key prefix applied to every virtual path. Empty by default.
        addressing_style: ``"virtual"`` or ``"path"``. Unset + custom
            endpoint defaults to path-style.
        signature_version: ``"s3v4"`` (default) or ``"s3"`` (SigV2).
    """

    bucket: str
    access_key_id: str
    secret_access_key: str
    region: str = ""
    endpoint_url: str = ""
    prefix: str = ""
    addressing_style: str = "virtual"
    signature_version: str = "s3v4"
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.bucket:
            raise ValueError("S3Config.bucket is required")
        if not self.access_key_id or not self.secret_access_key:
            raise ValueError("S3Config.access_key_id / secret_access_key are required")
        object.__setattr__(self, "prefix", self.prefix.strip("/"))

    @classmethod
    def from_kwargs(cls, **kwargs: Any) -> S3Config:
        """Build from a flat spec dict, ignoring unrecognised keys.

        Also accepts legacy boto3-style field names (``aws_access_key_id`` /
        ``aws_secret_access_key``) and community path-style aliases
        (``s3_force_path_style`` / ``force_path_style`` / ``path_style``).
        """
        kwargs = normalize_s3_spec_kwargs(kwargs)
        # Normalise legacy boto3-style key names.
        if "aws_access_key_id" in kwargs and "access_key_id" not in kwargs:
            kwargs["access_key_id"] = kwargs.pop("aws_access_key_id")
        if "aws_secret_access_key" in kwargs and "secret_access_key" not in kwargs:
            kwargs["secret_access_key"] = kwargs.pop("aws_secret_access_key")
        explicit_addressing = "addressing_style" in kwargs
        known = {f.name for f in cls.__dataclass_fields__.values()}
        extra = {k: v for k, v in kwargs.items() if k not in known}
        filtered = {k: v for k, v in kwargs.items() if k in known}
        if not explicit_addressing and str(filtered.get("endpoint_url") or "").strip():
            filtered["addressing_style"] = "path"
        return cls(**filtered, extra=extra)


class S3Backend(CloudStorageBackend):
    """S3-compatible virtual filesystem backend (boto3).

    Covers AWS S3, MinIO, and any S3-compatible store that accepts
    virtual-hosted style requests. All ``BackendProtocol`` methods are
    inherited from :class:`CloudStorageBackend`; only boto3 SDK calls
    are implemented here.
    """

    def __init__(self, config: S3Config) -> None:
        self._config = config
        self._client = self._build_client(config)
        self._alt_client: Any = None

    @property
    def _prefix(self) -> str:
        return self._config.prefix

    def _storage_error_types(self) -> tuple[type[BaseException], ...]:
        from botocore.exceptions import ClientError

        return (*super()._storage_error_types(), ClientError)

    @staticmethod
    def _build_client(config: S3Config) -> Any:
        import boto3

        kwargs: dict[str, Any] = {
            "aws_access_key_id": config.access_key_id,
            "aws_secret_access_key": config.secret_access_key,
            "config": _compat_s3_client_config(
                config.addressing_style,
                signature_version=config.signature_version or "s3v4",
            ),
        }
        if config.region:
            kwargs["region_name"] = config.region
        if config.endpoint_url:
            kwargs["endpoint_url"] = config.endpoint_url
        return boto3.client("s3", **kwargs)

    def _alternate_client(self) -> Any:
        if self._alt_client is None:
            current = (self._config.signature_version or "s3v4").lower()
            alt = "s3" if current == "s3v4" else "s3v4"
            alt_config = S3Config(
                bucket=self._config.bucket,
                access_key_id=self._config.access_key_id,
                secret_access_key=self._config.secret_access_key,
                region=self._config.region,
                endpoint_url=self._config.endpoint_url,
                prefix=self._config.prefix,
                addressing_style=self._config.addressing_style,
                signature_version=alt,
            )
            self._alt_client = self._build_client(alt_config)
        return self._alt_client

    def _list_objects_page(self, **kwargs: Any) -> dict[str, Any]:
        """``list_objects_v2`` with v1 / alternate-signature fallbacks."""
        return self._list_with_client(self._client, kwargs, allow_alt=True)

    def _list_with_client(
        self,
        client: Any,
        kwargs: dict[str, Any],
        *,
        allow_alt: bool,
    ) -> dict[str, Any]:
        from botocore.exceptions import ClientError

        try:
            return cast("dict[str, Any]", client.list_objects_v2(**kwargs))
        except ClientError as exc:
            if not (_is_s3_not_implemented(exc) or _is_s3_signature_mismatch(exc)):
                raise
            logger.info("list_objects_v2 rejected (%s); trying list_objects", exc)
            try:
                return _normalize_list_v1(client.list_objects(**_list_v1_kwargs(kwargs)))
            except ClientError as v1_exc:
                if allow_alt and (_is_s3_signature_mismatch(exc) or _is_s3_signature_mismatch(v1_exc)):
                    logger.info("retrying object list with the other S3 signature version")
                    alt = self._alternate_client()
                    result = self._list_with_client(alt, kwargs, allow_alt=False)
                    self._client = alt
                    return result
                raise v1_exc

    def _get_object_bytes(self, key: str) -> bytes | None:
        from botocore.exceptions import ClientError

        def _load(client: Any) -> bytes | None:
            try:
                resp = client.get_object(Bucket=self._config.bucket, Key=key)
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                http_status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
                if code in {"NoSuchKey", "404", "NotFound"} or http_status == 404:
                    return None
                raise
            return cast("bytes", resp["Body"].read())

        try:
            return _load(self._client)
        except ClientError as exc:
            if not (_is_s3_not_implemented(exc) or _is_s3_signature_mismatch(exc)):
                raise
            alt = self._alternate_client()
            body = _load(alt)
            self._client = alt
            return body

    # ------------------------------------------------------------------
    # SDK primitives
    # ------------------------------------------------------------------

    def _get_file_data(self, path: str) -> FileData | None:
        raw = self._get_object_bytes(self._key(path))
        if raw is None:
            return None
        return self._parse_body(raw)

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
            prefix_key += "/"

        entries: list[FileInfo] = []
        continuation_token: str | None = None
        while True:
            kwargs: dict[str, Any] = {
                "Bucket": self._config.bucket,
                "Prefix": prefix_key,
                "Delimiter": "/",
                "MaxKeys": 1000,
            }
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token
            resp = self._list_objects_page(**kwargs)

            for cp in resp.get("CommonPrefixes") or []:
                key = cp["Prefix"] if isinstance(cp, dict) else cp
                entries.append({"path": self._virtual_path(key.rstrip("/")), "is_dir": True})
            for obj in resp.get("Contents") or []:
                key = obj["Key"] if isinstance(obj, dict) else obj
                if key == prefix_key:
                    continue
                info: FileInfo = {"path": self._virtual_path(key), "is_dir": False}
                if isinstance(obj, dict):
                    if (size := obj.get("Size")) is not None:
                        info["size"] = int(size)
                    if last_mod := obj.get("LastModified"):
                        info["modified_at"] = str(last_mod)
                entries.append(info)

            if not resp.get("IsTruncated"):
                break
            continuation_token = resp.get("NextContinuationToken") or ""
            if not continuation_token:
                break

        entries.sort(key=lambda e: e["path"])
        return entries

    def _collect_recursive(self, path: str) -> dict[str, FileData]:
        from botocore.exceptions import ClientError

        prefix_key = self._key(path)
        if prefix_key and not prefix_key.endswith("/") and path != "/":
            prefix_key += "/"

        files: dict[str, FileData] = {}
        continuation_token: str | None = None
        while True:
            kwargs: dict[str, Any] = {
                "Bucket": self._config.bucket,
                "Prefix": prefix_key,
                "MaxKeys": 1000,
            }
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token
            resp = self._list_objects_page(**kwargs)

            for obj in resp.get("Contents") or []:
                key = obj["Key"] if isinstance(obj, dict) else obj
                if key.endswith("/"):
                    continue
                vp = self._virtual_path(key)
                try:
                    fd = self._get_file_data(vp)
                except ClientError:
                    continue
                if fd is not None:
                    files[vp] = fd

            if not resp.get("IsTruncated"):
                break
            continuation_token = resp.get("NextContinuationToken") or ""
            if not continuation_token:
                break
        return files

    def _iter_prefix_object_keys(self, path: str) -> Any:
        prefix_key = self._prefix_key(path)
        continuation_token: str | None = None
        while True:
            kwargs: dict[str, Any] = {
                "Bucket": self._config.bucket,
                "Prefix": prefix_key,
                "MaxKeys": 1000,
            }
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token
            resp = self._list_objects_page(**kwargs)
            for obj in resp.get("Contents") or []:
                yield obj["Key"] if isinstance(obj, dict) else obj
            if not resp.get("IsTruncated"):
                break
            continuation_token = resp.get("NextContinuationToken") or ""
            if not continuation_token:
                break

    def _prefix_has_objects(self, path: str) -> bool:
        resp = self._list_objects_page(
            Bucket=self._config.bucket,
            Prefix=self._prefix_key(path),
            MaxKeys=1,
        )
        return bool(resp.get("Contents"))

    def _copy_object(self, src: str, dest: str) -> None:
        self._client.copy_object(
            Bucket=self._config.bucket,
            Key=self._key(dest),
            CopySource={"Bucket": self._config.bucket, "Key": self._key(src)},
        )

    def delete_object(self, path: str) -> None:
        """Delete the S3 object backing ``path``."""
        self._client.delete_object(Bucket=self._config.bucket, Key=self._key(path))

    def delete_prefix(self, path: str) -> int:
        """Delete every object under ``path``; return count of removed keys."""
        deleted = 0
        for key in self._iter_prefix_object_keys(path):
            self._client.delete_object(Bucket=self._config.bucket, Key=key)
            deleted += 1
        return deleted


# ---------------------------------------------------------------------------
# COS fallback spec converter
# ---------------------------------------------------------------------------


def cos_spec_to_s3_compat(spec: dict[str, Any]) -> dict[str, Any] | None:
    """Return an S3-protocol spec equivalent to a COS spec.

    Used when the native ``cos-python-sdk-v5`` is unavailable but boto3
    can still talk to Tencent COS via the S3-compatible API.
    """
    if spec.get("type") != "cos":
        return None
    bucket = spec.get("bucket")
    region = spec.get("region")
    secret_id = spec.get("secret_id")
    secret_key = spec.get("secret_key")
    if not all((bucket, region, secret_id, secret_key)):
        return None
    endpoint = spec.get("endpoint") or f"cos.{region}.myqcloud.com"
    if "://" not in str(endpoint):
        endpoint = f"https://{endpoint}"
    out: dict[str, Any] = {
        "type": "s3",
        "bucket": bucket,
        "access_key_id": secret_id,
        "secret_access_key": secret_key,
        "region": region,
        "endpoint_url": endpoint,
        "addressing_style": "virtual",
    }
    prefix = spec.get("prefix")
    if prefix:
        out["prefix"] = prefix
    return out


# Backward-compat aliases for code that imported from the old module names.
S3CompatConfig = S3Config
S3CompatBackend = S3Backend

__all__ = [
    "S3Backend",
    "S3CompatBackend",  # alias
    "S3CompatConfig",  # alias
    "S3Config",
    "cos_spec_to_s3_compat",
    "normalize_s3_spec_kwargs",
]
