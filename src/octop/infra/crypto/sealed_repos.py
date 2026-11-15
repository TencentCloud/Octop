"""Repo wrappers that seal TEXT secrets at rest and open them on read."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from octop.infra.crypto.fernet import (
    PURPOSE_PROVIDER,
    PURPOSE_SEARCH,
    PURPOSE_STORAGE,
    PURPOSE_VOICE,
    decrypt_json,
    encrypt_json,
    open_text,
    seal_text,
)
from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import UNSET, now_ts
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


class SealedUserSearchKeyRepo:
    """Per-user web-search credentials as sealed ``secrets`` KV entries.

    ``user_search_key:{user_id}:{provider_id}`` maps to the Fernet ciphertext
    of ``{"env": {ENV_NAME: value}}`` (``PURPOSE_SEARCH``). The whole required
    env set for a provider is stored together so a personal key never mixes
    with a global one (e.g. Google's ``GOOGLE_API_KEY`` + ``GOOGLE_CSE_ID``).
    """

    _KEY_PREFIX = "user_search_key:"

    def __init__(self, secrets: SecretRepo) -> None:
        self._secrets = secrets

    @classmethod
    def _key(cls, user_id: int, provider_id: str) -> str:
        return f"{cls._KEY_PREFIX}{user_id}:{provider_id}"

    def set_env(self, user_id: int, provider_id: str, env: dict[str, str]) -> int:
        """Store the sealed env mapping; returns its ``updated_at`` (unix seconds)."""
        self._secrets.put(
            self._key(user_id, provider_id),
            encrypt_json(self._secrets, PURPOSE_SEARCH, {"env": dict(env)}),
        )
        return now_ts()

    def _decode(self, blob: bytes) -> dict[str, str]:
        payload = decrypt_json(self._secrets, PURPOSE_SEARCH, blob)
        raw = payload.get("env")
        if not isinstance(raw, dict):
            return {}
        return {
            str(k): str(v)
            for k, v in raw.items()
            if isinstance(k, str) and isinstance(v, str) and v
        }

    def get_env(self, user_id: int, provider_id: str) -> dict[str, str] | None:
        """Decrypt one provider's personal env mapping (runtime only)."""
        blob = self._secrets.get(self._key(user_id, provider_id))
        if blob is None:
            return None
        return self._decode(blob)

    def get_all_env(self, user_id: int) -> dict[str, str]:
        """Decrypt every provider's personal env for one user in a single scan.

        Used by the per-turn hot path; keeps it to one ``secrets`` query instead
        of one per provider.
        """
        out: dict[str, str] = {}
        for _k, blob, _created_at, _rotated_at in self._secrets.list_prefix(
            f"{self._KEY_PREFIX}{user_id}:"
        ):
            out.update(self._decode(blob))
        return out

    def list_for_user(self, user_id: int) -> list[tuple[str, int]]:
        """``(provider_id, updated_at)`` pairs — never the key material."""
        prefix = f"{self._KEY_PREFIX}{user_id}:"
        out: list[tuple[str, int]] = []
        for k, _v, created_at, rotated_at in self._secrets.list_prefix(prefix):
            out.append((k[len(prefix) :], rotated_at or created_at))
        return out

    def delete_key(self, user_id: int, provider_id: str) -> bool:
        return self._secrets.delete(self._key(user_id, provider_id))

    def delete_for_user(self, user_id: int) -> int:
        """Drop every personal search key this user stored (user-deletion cleanup)."""
        return self._secrets.delete_prefix(f"{self._KEY_PREFIX}{user_id}:")


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
