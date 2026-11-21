"""Volcengine TOS storage using the official SDK and the harness file protocol."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any
from urllib.parse import unquote

from deepagents.backends.protocol import FileData, FileInfo
from octop_harness.backends.cloud_storage_base import CloudStorageBackend

_MISSING = "TOS backend requires the optional dependency 'tos'. Install with: uv pip install 'tos>=2.9,<3'."


def _import_tos() -> tuple[Any, type[BaseException], type[BaseException]]:
    try:
        from tos import TosClientV2
        from tos.exceptions import TosClientError, TosServerError
    except ImportError as exc:
        raise ImportError(_MISSING) from exc
    return TosClientV2, TosServerError, TosClientError


class TOSBackend(CloudStorageBackend):
    """TOS-backed virtual filesystem; file envelopes match other cloud backends."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        endpoint: str,
        access_key_id: str,
        secret_access_key: str,
        prefix: str = "",
        security_token: str | None = None,
    ) -> None:
        if not all((bucket, region, endpoint, access_key_id, secret_access_key)):
            raise ValueError("TOS configuration incomplete")
        client_cls, server_error, client_error = _import_tos()
        self._bucket = bucket
        self._key_prefix = prefix.strip("/")
        self._server_error = server_error
        self._client_error = client_error
        self._client = client_cls(
            ak=access_key_id,
            sk=secret_access_key,
            endpoint=endpoint if "://" in endpoint else f"https://{endpoint}",
            region=region,
            security_token=security_token,
        )

    @property
    def _prefix(self) -> str:
        return self._key_prefix

    def _request(self, operation: Callable[..., Any], **kwargs: Any) -> Any:
        """Expose SDK errors without its verbose headers or request URL."""
        try:
            return operation(**kwargs)
        except self._server_error as exc:
            code = getattr(exc, "code", "")
            message = getattr(exc, "message", None) or str(exc)
            if code == "NoSuchKey":
                raise FileNotFoundError(message) from exc
            raise RuntimeError(f"TOS ({code}): {message}") from exc
        except self._client_error as exc:
            message = getattr(exc, "message", None) or str(exc)
            raise RuntimeError(f"TOS: {message}") from exc

    def _get_file_data(self, path: str) -> FileData | None:
        if path.endswith("/"):
            return None
        try:
            response = self._request(
                self._client.get_object, bucket=self._bucket, key=self._key(path)
            )
            # Iteration consumes the response and verifies the SDK's CRC checksum.
            raw = self._request(lambda: b"".join(response))
        except FileNotFoundError:
            return None
        return self._parse_body(raw)

    def _put_file_data(self, path: str, file_data: FileData) -> None:
        self._request(
            self._client.put_object,
            bucket=self._bucket,
            key=self._key(path),
            content=self._encode_file_data(file_data),
            content_type="application/json",
        )

    def _pages(self, path: str, *, delimiter: str | None = None) -> Iterator[Any]:
        token = None
        while True:
            page = self._request(
                self._client.list_objects_type2,
                bucket=self._bucket,
                prefix=self._prefix_key(path),
                delimiter=delimiter,
                continuation_token=token,
                max_keys=1000,
                encoding_type="url",
                list_only_once=True,
            )
            yield page
            if not page.is_truncated:
                return
            next_token = page.next_continuation_token
            if not next_token or next_token == token:
                raise RuntimeError("TOS listing returned an invalid continuation token")
            token = next_token

    def _ls_entries(self, path: str) -> list[FileInfo]:
        entries: list[FileInfo] = []
        prefix = self._prefix_key(path)
        for page in self._pages(path, delimiter="/"):
            for common in page.common_prefixes:
                entries.append(
                    {
                        "path": self._virtual_path(unquote(common.prefix)),
                        "is_dir": True,
                    }
                )
            for obj in page.contents:
                key = unquote(obj.key)
                if key == prefix:
                    continue
                info: FileInfo = {
                    "path": self._virtual_path(key),
                    "is_dir": key.endswith("/"),
                    "size": obj.size or 0,
                }
                if obj.last_modified:
                    info["modified_at"] = obj.last_modified.isoformat()
                entries.append(info)
        return entries

    def _collect_recursive(self, path: str) -> dict[str, FileData]:
        files: dict[str, FileData] = {}
        for key in self._iter_prefix_object_keys(path):
            if key.endswith("/"):
                continue
            virtual = self._virtual_path(key)
            data = self._get_file_data(virtual)
            if data is not None:
                files[virtual] = data
        return files

    def _iter_prefix_object_keys(self, path: str) -> Iterator[str]:
        for page in self._pages(path):
            for obj in page.contents:
                yield unquote(obj.key)

    def _prefix_has_objects(self, path: str) -> bool:
        result = self._request(
            self._client.list_objects_type2,
            bucket=self._bucket,
            prefix=self._prefix_key(path),
            max_keys=1,
            list_only_once=True,
        )
        return bool(result.contents)

    def _copy_object(self, src: str, dest: str) -> None:
        # The shared move helper drops the root marker's trailing slash.
        # Preserve it so a moved directory cannot become an empty file.
        destination = self._prefix_key(dest) if src.endswith("/") else self._key(dest)
        self._request(
            self._client.copy_object,
            bucket=self._bucket,
            key=destination,
            src_bucket=self._bucket,
            src_key=self._key(src),
        )

    def _put_dir_marker(self, virtual_dir: str) -> None:
        self._request(
            self._client.put_object,
            bucket=self._bucket,
            key=self._prefix_key(virtual_dir),
            content=b"",
        )

    def delete_object(self, path: str) -> None:
        self._request(self._client.delete_object, bucket=self._bucket, key=self._key(path))

    def delete_prefix(self, path: str) -> int:
        deleted = 0
        for key in self._iter_prefix_object_keys(path):
            self._request(self._client.delete_object, bucket=self._bucket, key=key)
            deleted += 1
        return deleted

    def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            close()


def tos_backend_from_spec(spec: dict[str, Any]) -> TOSBackend:
    """Build a live client from a harness-style ``type=tos`` spec."""
    token = spec.get("security_token")
    return TOSBackend(
        bucket=str(spec.get("bucket") or ""),
        region=str(spec.get("region") or ""),
        endpoint=str(spec.get("endpoint") or ""),
        access_key_id=str(spec.get("access_key_id") or ""),
        secret_access_key=str(spec.get("secret_access_key") or ""),
        prefix=str(spec.get("prefix") or ""),
        security_token=str(token) if token else None,
    )
