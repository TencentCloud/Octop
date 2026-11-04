"""Volcengine TOS backend without the official SDK."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import pytest

from octop.infra.backend.adapter import row_to_backend_spec
from octop.infra.backend.resolve_backend import materialize_octop_specs
from octop.infra.backend.tos_backend import TOSBackend, tos_backend_from_spec
from octop.infra.db.repos.backends import BackendRow


class _ServerError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class _ClientError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class _Prefix:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix


class _Object:
    def __init__(self, key: str, size: int) -> None:
        self.key = key
        self.size = size
        self.last_modified = None


class _Page:
    def __init__(
        self,
        contents: list[_Object],
        common_prefixes: list[_Prefix],
        *,
        truncated: bool = False,
        token: str | None = None,
    ) -> None:
        self.contents = contents
        self.common_prefixes = common_prefixes
        self.is_truncated = truncated
        self.next_continuation_token = token


class _FakeClient:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.store: dict[str, bytes] = {}

    def put_object(
        self, *, bucket: str, key: str, content: bytes, content_type: str | None = None
    ) -> None:
        del bucket, content_type
        self.store[key] = content

    def get_object(self, *, bucket: str, key: str) -> list[bytes]:
        del bucket
        if key not in self.store:
            raise _ServerError("NoSuchKey", "missing")
        return [self.store[key]]

    def delete_object(self, *, bucket: str, key: str) -> None:
        del bucket
        self.store.pop(key, None)

    def copy_object(self, *, bucket: str, key: str, src_bucket: str, src_key: str) -> None:
        del bucket, src_bucket
        self.store[key] = self.store[src_key]

    def list_objects_type2(self, **kwargs: Any) -> _Page:
        prefix = str(kwargs.get("prefix") or "")
        delimiter = kwargs.get("delimiter")
        token = kwargs.get("continuation_token")
        keys = sorted(key for key in self.store if key.startswith(prefix))
        if token:
            keys = [key for key in keys if key > token]
        max_keys = int(kwargs.get("max_keys") or 1000)
        page_keys = keys[:max_keys]
        truncated = len(keys) > max_keys
        next_token = page_keys[-1] if truncated and page_keys else None
        contents: list[_Object] = []
        commons: dict[str, _Prefix] = {}
        for key in page_keys:
            shown = quote(key, safe="/")
            if delimiter and delimiter in key[len(prefix) :]:
                head = key[len(prefix) :].split(delimiter, 1)[0]
                commons[prefix + head + delimiter] = _Prefix(
                    quote(prefix + head + delimiter, safe="/")
                )
                continue
            contents.append(_Object(shown, len(self.store[key])))
        return _Page(contents, list(commons.values()), truncated=truncated, token=next_token)

    def close(self) -> None:
        return None


def _row(**overrides: Any) -> BackendRow:
    payload: dict[str, Any] = {
        "id": 1,
        "name": "volc",
        "kind": "tos",
        "endpoint": "tos-cn-beijing.volces.com",
        "access_key": "AK",
        "secret_key": "SK",
        "bucket": "bucket",
        "region": "cn-beijing",
        "config_json": '{"prefix": "agents", "security_token": "sts"}',
        "note": None,
        "enabled": 1,
        "created_at": 0,
        "updated_at": 0,
    }
    payload.update(overrides)
    return BackendRow(**payload)


@pytest.fixture
def fake_sdk(monkeypatch: pytest.MonkeyPatch) -> _FakeClient:
    holder: dict[str, _FakeClient] = {}

    def _build(**kwargs: Any) -> _FakeClient:
        client = _FakeClient(**kwargs)
        holder["client"] = client
        return client

    monkeypatch.setattr(
        "octop.infra.backend.tos_backend._import_tos",
        lambda: (_build, _ServerError, _ClientError),
    )
    return holder  # type: ignore[return-value]


def test_row_to_backend_spec_tos() -> None:
    spec = row_to_backend_spec(_row())
    assert spec == {
        "type": "tos",
        "bucket": "bucket",
        "region": "cn-beijing",
        "endpoint": "tos-cn-beijing.volces.com",
        "access_key_id": "AK",
        "secret_access_key": "SK",
        "prefix": "agents",
        "security_token": "sts",
    }
    assert row_to_backend_spec(_row(endpoint=None)) is None


def test_materialize_replaces_tos_inside_composite(fake_sdk: dict[str, _FakeClient]) -> None:
    spec = {
        "type": "composite",
        "default": {"type": "filesystem", "root_dir": "/tmp"},
        "routes": {"/cloud": row_to_backend_spec(_row())},
    }
    prepared = materialize_octop_specs(spec)
    assert spec["routes"]["/cloud"]["type"] == "tos"
    assert isinstance(prepared["routes"]["/cloud"], TOSBackend)
    assert prepared["default"]["type"] == "filesystem"
    assert fake_sdk["client"].kwargs["security_token"] == "sts"
    assert fake_sdk["client"].kwargs["endpoint"].startswith("https://")


def test_roundtrip_list_and_missing_key(fake_sdk: dict[str, _FakeClient]) -> None:
    backend = tos_backend_from_spec(
        {
            "bucket": "bucket",
            "region": "cn-beijing",
            "endpoint": "tos-cn-beijing.volces.com",
            "access_key_id": "AK",
            "secret_access_key": "SK",
        }
    )
    written = backend.write("/notes/你好.txt", "hello")
    assert written.error is None
    read = backend.read("/notes/你好.txt")
    assert read.file_data is not None
    assert "hello" in str(read.file_data.get("content"))
    listed = backend.ls("/notes")
    assert listed.error is None
    paths = [entry.get("path") for entry in listed.entries or []]
    assert "/notes/你好.txt" in paths
    missing = backend.read("/missing.txt")
    assert missing.error
    backend.delete_object("/notes/你好.txt")
    assert fake_sdk["client"].store == {}
    backend.close()
