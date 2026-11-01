"""Repo wrappers that seal TEXT secrets at rest and open them on read."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from octop.infra.crypto.fernet import (
    PURPOSE_PROVIDER,
    PURPOSE_STORAGE,
    PURPOSE_VOICE,
    open_text,
    seal_text,
)
from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import UNSET
from octop.infra.db.repos.backends import BackendRepo, BackendRow
from octop.infra.db.repos.providers import ProviderRepo, ProviderRow
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.voice_providers import VoiceProviderRepo, VoiceProviderRow


class SealedProviderRepo:
    """Delegate to ``ProviderRepo``; encrypt ``api_key`` in the database."""

    def __init__(self, inner: ProviderRepo, secrets: SecretRepo) -> None:
        self._inner = inner
        self._secrets = secrets

    @property
    def _db(self) -> DatabasePool:
        """Expose the inner pool so runtime rebind checks keep working."""
        return self._inner._db

    def create(self, *, api_key: str | None = None, **kwargs: Any) -> int:
        return self._inner.create(
            api_key=seal_text(self._secrets, PURPOSE_PROVIDER, api_key),
            **kwargs,
        )

    def get(self, provider_id: int) -> ProviderRow | None:
        return self._open(self._inner.get(provider_id))

    def get_by_name(self, name: str) -> ProviderRow | None:
        return self._open(self._inner.get_by_name(name))

    def list_all(self) -> list[ProviderRow]:
        return [self._open_row(item) for item in self._inner.list_all()]

    def update(
        self, provider_id: int, *, api_key: str | None | object = UNSET, **kwargs: Any
    ) -> None:
        sealed: str | None | object = UNSET
        if api_key is not UNSET:
            sealed = (
                None
                if api_key is None
                else seal_text(self._secrets, PURPOSE_PROVIDER, str(api_key))
            )
        self._inner.update(provider_id, api_key=sealed, **kwargs)

    def delete(self, provider_id: int) -> None:
        self._inner.delete(provider_id)

    def find_referencing_agent_ids(self, agent_repo: Any, provider_name: str) -> list[str]:
        return self._inner.find_referencing_agent_ids(agent_repo, provider_name)

    def _open(self, row: ProviderRow | None) -> ProviderRow | None:
        if row is None:
            return None
        return self._open_row(row)

    def _open_row(self, row: ProviderRow) -> ProviderRow:
        return replace(row, api_key=open_text(self._secrets, PURPOSE_PROVIDER, row.api_key))


class SealedVoiceProviderRepo:
    """Delegate to ``VoiceProviderRepo``; encrypt ``api_key`` in the database."""

    def __init__(self, inner: VoiceProviderRepo, secrets: SecretRepo) -> None:
        self._inner = inner
        self._secrets = secrets

    @property
    def _db(self) -> DatabasePool:
        return self._inner._db

    def create(self, *, api_key: str | None = None, **kwargs: Any) -> int:
        return self._inner.create(
            api_key=seal_text(self._secrets, PURPOSE_VOICE, api_key),
            **kwargs,
        )

    def get(self, provider_id: int) -> VoiceProviderRow | None:
        return self._open(self._inner.get(provider_id))

    def get_by_name(self, name: str) -> VoiceProviderRow | None:
        return self._open(self._inner.get_by_name(name))

    def list_all(self) -> list[VoiceProviderRow]:
        return [self._open_row(item) for item in self._inner.list_all()]

    def update(self, provider_id: int, *, api_key: str | None = None, **kwargs: Any) -> None:
        # ``partial_updates`` skips ``None``; only seal when a new key is provided.
        sealed = seal_text(self._secrets, PURPOSE_VOICE, api_key) if api_key is not None else None
        self._inner.update(provider_id, api_key=sealed, **kwargs)

    def delete(self, provider_id: int) -> None:
        self._inner.delete(provider_id)

    def _open(self, row: VoiceProviderRow | None) -> VoiceProviderRow | None:
        if row is None:
            return None
        return self._open_row(row)

    def _open_row(self, row: VoiceProviderRow) -> VoiceProviderRow:
        return replace(row, api_key=open_text(self._secrets, PURPOSE_VOICE, row.api_key))


class SealedBackendRepo:
    """Delegate to ``BackendRepo``; encrypt ``secret_key`` in the database."""

    def __init__(self, inner: BackendRepo, secrets: SecretRepo) -> None:
        self._inner = inner
        self._secrets = secrets

    @property
    def _db(self) -> DatabasePool:
        return self._inner._db

    def create(self, *, secret_key: str | None = None, **kwargs: Any) -> int:
        return self._inner.create(
            secret_key=seal_text(self._secrets, PURPOSE_STORAGE, secret_key),
            **kwargs,
        )

    def get(self, backend_id: int) -> BackendRow | None:
        return self._open(self._inner.get(backend_id))

    def get_by_name(self, name: str) -> BackendRow | None:
        return self._open(self._inner.get_by_name(name))

    def list_all(self) -> list[BackendRow]:
        return [self._open_row(item) for item in self._inner.list_all()]

    def update(self, backend_id: int, *, secret_key: str | None = None, **kwargs: Any) -> None:
        sealed = (
            seal_text(self._secrets, PURPOSE_STORAGE, secret_key)
            if secret_key is not None
            else None
        )
        self._inner.update(backend_id, secret_key=sealed, **kwargs)

    def delete(self, backend_id: int) -> None:
        self._inner.delete(backend_id)

    def _open(self, row: BackendRow | None) -> BackendRow | None:
        if row is None:
            return None
        return self._open_row(row)

    def _open_row(self, row: BackendRow) -> BackendRow:
        return replace(row, secret_key=open_text(self._secrets, PURPOSE_STORAGE, row.secret_key))
