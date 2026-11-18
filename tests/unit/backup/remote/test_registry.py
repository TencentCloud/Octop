"""Registry and stub provider coverage for remote backup."""

from __future__ import annotations

import pytest

from octop.infra.backup.remote import get_provider, register_provider
from octop.infra.backup.remote.types import MirrorResult, RemoteObject
from octop.infra.errors import ErrorCode, OctopError


@pytest.mark.asyncio
async def test_s3_and_dropbox_stubs_raise_not_implemented() -> None:
    for kind in ("s3", "dropbox"):
        provider = get_provider(kind)
        with pytest.raises(OctopError) as exc_info:
            await provider.test()
        assert exc_info.value.code == ErrorCode.BACKUP_REMOTE_UNSUPPORTED
        assert "not implemented" in str(exc_info.value).lower()


def test_unknown_kind_raises() -> None:
    with pytest.raises(OctopError) as exc_info:
        get_provider("not-a-real-provider")
    assert exc_info.value.code == ErrorCode.BACKUP_REMOTE_UNSUPPORTED
    assert "unsupported" in str(exc_info.value).lower()


def test_register_provider_overrides_factory() -> None:
    class _Fake:
        async def test(self) -> None:
            return None

        async def put(self, local_path, remote_name):  # type: ignore[no-untyped-def]
            return MirrorResult(status="remote_ok")

        async def list(self):  # type: ignore[no-untyped-def]
            return [RemoteObject(name="a.tar.gz", size=1)]

        async def get(self, remote_name, dest) -> None:  # type: ignore[no-untyped-def]
            return None

        async def delete(self, remote_name) -> None:  # type: ignore[no-untyped-def]
            return None

    register_provider("webdav-test-override", lambda **_kwargs: _Fake())
    try:
        provider = get_provider("webdav-test-override")
        assert isinstance(provider, _Fake)
    finally:
        from octop.infra.backup.remote import registry as reg

        reg._REGISTRY.pop("webdav-test-override", None)
