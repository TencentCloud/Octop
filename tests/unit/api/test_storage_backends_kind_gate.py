"""``patch_storage_backend`` must apply the OpenSandbox dependency gate too.

``create_storage_backend`` calls ``_ensure_opensandbox_sdk`` unconditionally,
and ``patch_storage_backend`` already computes the effective kind
(``next_kind = body.kind or row.kind``) — but the gate sits behind
``if body.enabled is True:``.

The dashboard's edit form never sends ``enabled`` at all (it posts only
kind/bucket/region/endpoint/config_json/note/credentials/name), and
``BackendRepo.update`` leaves the column untouched when ``enabled is None``.
So changing an **already enabled** backend to ``kind="opensandbox"`` skips the
gate and leaves the row enabled — the admin gets a 200 and only finds out later,
from a runtime error, instead of the actionable ``STORAGE_BACKEND_DEPS_FAILED``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from octop.api.routers import storage_backends
from octop.infra.backend import browse as browse_mod
from octop.infra.db.repos.backends import BackendRow
from octop.infra.errors import ErrorCode, OctopError


def _row(**overrides) -> BackendRow:
    base = {
        "id": 7,
        "name": "sb",
        "kind": "s3",
        "endpoint": None,
        "access_key": None,
        "secret_key": None,
        "bucket": None,
        "region": None,
        "config_json": None,
        "note": None,
        "enabled": 1,
        "created_at": 1,
        "updated_at": 1,
    }
    base.update(overrides)
    return BackendRow(**base)  # type: ignore[arg-type]


def _server(row: BackendRow) -> SimpleNamespace:
    repo = MagicMock()
    repo.get.return_value = row
    repo.get_by_name.return_value = None
    return SimpleNamespace(
        services=SimpleNamespace(storage_backend_repo=repo),
        app_runtime=None,
    )


async def _no_release(_backend_id: int) -> None:
    return None


@pytest.fixture
def gate(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every kind the dependency gate is asked about."""
    seen: list[str] = []

    def _ensure(kind: str) -> None:
        seen.append(kind)

    monkeypatch.setattr(storage_backends, "_ensure_opensandbox_sdk", _ensure)
    # release_browse_session is imported inside the route body, so patch the
    # module it is imported from rather than the router module.
    monkeypatch.setattr(browse_mod, "release_browse_session", _no_release)
    return seen


async def _patch(server: SimpleNamespace, **body) -> dict:
    return await storage_backends.patch_storage_backend(
        backend_id=7,
        body=storage_backends.StorageBackendPatchBody(**body),
        server=server,
        _=None,
    )


@pytest.mark.asyncio
async def test_patch_to_opensandbox_runs_the_dependency_gate(
    gate: list[str],
) -> None:
    """Enabled row, kind switched, ``enabled`` omitted — exactly what the UI sends."""
    server = _server(_row(kind="s3", enabled=1))

    await _patch(server, kind="opensandbox")

    assert "opensandbox" in gate, "the OpenSandbox dependency gate was skipped"


@pytest.mark.asyncio
async def test_patch_rejects_when_sdk_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """The gate must actually reject, not just be consulted."""
    monkeypatch.setattr(browse_mod, "release_browse_session", _no_release)

    def _boom(kind: str) -> None:
        if kind == "opensandbox":
            raise OctopError(
                ErrorCode.STORAGE_BACKEND_DEPS_FAILED, "OpenSandbox SDK is not installed."
            )

    monkeypatch.setattr(storage_backends, "_ensure_opensandbox_sdk", _boom)
    server = _server(_row(kind="s3", enabled=1))

    with pytest.raises(OctopError) as exc_info:
        await _patch(server, kind="opensandbox")
    assert exc_info.value.code == ErrorCode.STORAGE_BACKEND_DEPS_FAILED


@pytest.mark.asyncio
async def test_patch_keeps_the_row_disabled_when_the_gate_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rejected change must not be written, whatever the caller sent."""
    monkeypatch.setattr(browse_mod, "release_browse_session", _no_release)

    def _boom(kind: str) -> None:
        if kind == "opensandbox":
            raise OctopError(ErrorCode.STORAGE_BACKEND_DEPS_FAILED, "nope")

    monkeypatch.setattr(storage_backends, "_ensure_opensandbox_sdk", _boom)
    server = _server(_row(kind="s3", enabled=1))

    with pytest.raises(OctopError):
        await _patch(server, kind="opensandbox", enabled=True)

    server.services.storage_backend_repo.update.assert_not_called()


@pytest.mark.asyncio
async def test_patch_that_keeps_a_non_opensandbox_kind_still_skips_the_gate(
    gate: list[str],
) -> None:
    """Ordinary edits must not start paying for the dependency check."""
    server = _server(_row(kind="s3", enabled=1))

    await _patch(server, bucket="my-bucket")

    assert "opensandbox" not in gate


@pytest.mark.asyncio
async def test_patch_away_from_opensandbox_does_not_require_the_sdk(
    gate: list[str],
) -> None:
    """Dropping the kind must not be blocked by the dependency it removes."""
    server = _server(_row(kind="opensandbox", enabled=1))

    await _patch(server, kind="s3")

    assert "opensandbox" not in gate


@pytest.mark.asyncio
async def test_create_and_patch_agree_on_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """The two entry points must not disagree about the same kind."""
    asked: list[str] = []

    def _record(kind: str) -> None:
        asked.append(kind)

    monkeypatch.setattr(storage_backends, "_ensure_opensandbox_sdk", _record)
    server = _server(_row(kind="s3", enabled=1))
    server.services.storage_backend_repo.get_by_name.return_value = None

    await storage_backends.create_storage_backend(
        body=storage_backends.StorageBackendCreateBody(name="new-sb", kind="opensandbox"),
        server=server,
        _=None,
    )
    create_asked = list(asked)

    asked.clear()
    await _patch(server, kind="opensandbox")
    patch_asked = list(asked)

    assert create_asked == patch_asked, "create and patch disagree about the same kind"
