"""Langfuse settings persistence for the agent runtime."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)

_KEY_ENABLED = "observability_langfuse_enabled"
_KEY_PUBLIC = "observability_langfuse_public_key"
_KEY_HOST = "observability_langfuse_host"
_SECRET_KEY = "langfuse_secret_key"
# Dedicated Fernet key row (same shape as ``connector_fernet`` / ``sso_fernet``) so a
# Langfuse credential never inherits the SSO key lifecycle.
_FERNET_KEY = "langfuse_fernet"
# Fernet token fast-sieve only -- never the decision (the decision is ``Fernet.decrypt``).
_FERNET_TOKEN_PREFIX = b"gAAAAA"


def verify_langfuse_credentials(host: str, public_key: str, secret_key: str) -> dict[str, Any]:
    """Verify Langfuse keys via the public projects API.

    Uses raw HTTP instead of ``Langfuse.auth_check()`` for older self-hosted
    instances that omit newer response fields (e.g. ``organization``).
    """
    base = host.strip().rstrip("/")
    url = f"{base}/api/public/projects"
    token = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    req = urllib.request.Request(  # noqa: S310
        url,
        headers={"Authorization": f"Basic {token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            status = resp.status
            raw = resp.read().decode()
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            return {"ok": False, "error": "authentication failed"}
        return {"ok": False, "error": f"HTTP {exc.code}"}
    except urllib.error.URLError as exc:
        return {"ok": False, "error": str(exc.reason)}

    if status >= 400:
        return {"ok": False, "error": f"HTTP {status}"}

    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "error": "invalid JSON response from Langfuse"}

    projects = body.get("data") if isinstance(body, dict) else None
    if not isinstance(projects, list) or not projects:
        return {"ok": False, "error": "no project found for the keys provided"}
    return {"ok": True}


@dataclass(frozen=True)
class LangfuseSettings:
    """Admin-visible Langfuse configuration (secret value never exposed)."""

    enabled: bool
    public_key: str
    host: str
    secret_key_set: bool

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.public_key and self.host and self.secret_key_set)


class LangfuseSettingsStore:
    """Read/write Langfuse credentials in settings + secrets tables."""

    def __init__(self, *, settings_repo: SettingsRepo, secret_repo: SecretRepo) -> None:
        self._settings = settings_repo
        self._secrets = secret_repo

    def _fernet(self) -> Fernet:
        """Existing dedicated Fernet for the stored Langfuse credential.

        Fail-closed: a missing or malformed key row raises -- it must never be silently
        regenerated, because that would leave already-stored ciphertext undecryptable.
        """
        raw_key = self._secrets.get(_FERNET_KEY)
        if raw_key is None:
            raise OctopError(
                ErrorCode.INTERNAL_ERROR,
                f"secrets row k={_FERNET_KEY} is missing: stored Langfuse credential "
                "cannot be decrypted (run the migration before serving requests)",
            )
        try:
            return Fernet(raw_key)
        except (TypeError, ValueError) as exc:
            logger.error("langfuse key row unusable (k=%s · %s)", _FERNET_KEY, type(exc).__name__)
            raise OctopError(
                ErrorCode.INTERNAL_ERROR,
                f"secrets row k={_FERNET_KEY} is not a valid Fernet key: stored Langfuse "
                "credential cannot be decrypted",
            ) from None

    def _write_fernet(self) -> Fernet:
        """Fernet used on the write path -- creates the key only when that is lossless.

        Ordering: the key must exist before any ciphertext is written, and a credential
        that already looks encrypted must never be orphaned by generating a fresh key.
        """
        if self._secrets.get(_FERNET_KEY) is not None:
            return self._fernet()
        stored = self._secrets.get(_SECRET_KEY)
        if stored is not None and stored.startswith(_FERNET_TOKEN_PREFIX):
            raise OctopError(
                ErrorCode.INTERNAL_ERROR,
                f"secrets row k={_SECRET_KEY} looks encrypted but k={_FERNET_KEY} is missing: "
                "refusing to generate a new key (the old ciphertext would become undecryptable)",
            )
        created = self._secrets.get_or_create(_FERNET_KEY, Fernet.generate_key)
        return Fernet(created)

    def _decrypt(self, token: bytes) -> str:
        """Decrypt a stored credential; every failure raises (no plaintext fallback)."""
        fernet = self._fernet()
        try:
            return fernet.decrypt(token).decode("utf-8")
        except InvalidToken:
            logger.error("langfuse credential not decryptable (k=%s · InvalidToken)", _SECRET_KEY)
            raise OctopError(
                ErrorCode.INTERNAL_ERROR,
                f"secrets row k={_SECRET_KEY} is not decryptable: key mismatch or corrupted value",
            ) from None
        except ValueError as exc:
            logger.error(
                "langfuse credential undecodable (k=%s · %s)", _SECRET_KEY, type(exc).__name__
            )
            raise OctopError(
                ErrorCode.INTERNAL_ERROR,
                f"secrets row k={_SECRET_KEY} is not a valid UTF-8 credential after decryption",
            ) from None

    def load(self) -> LangfuseSettings:
        enabled = (self._settings.get(_KEY_ENABLED) or "").lower() in {"1", "true", "yes"}
        public_key = (self._settings.get(_KEY_PUBLIC) or "").strip()
        host = (self._settings.get(_KEY_HOST) or "").strip().rstrip("/")
        secret_key_set = self._secrets.get(_SECRET_KEY) is not None
        return LangfuseSettings(
            enabled=enabled,
            public_key=public_key,
            host=host,
            secret_key_set=secret_key_set,
        )

    def save(
        self,
        *,
        enabled: bool,
        public_key: str,
        host: str,
        secret_key: str | None = None,
    ) -> LangfuseSettings:
        public_key = public_key.strip()
        host = host.strip().rstrip("/")
        if enabled and (not public_key or not host):
            raise OctopError(
                ErrorCode.SLASH_BAD_ARGS,
                "public_key and host are required when Langfuse is enabled",
            )
        if enabled and not (secret_key or self._secrets.get(_SECRET_KEY) is not None):
            raise OctopError(
                ErrorCode.SLASH_BAD_ARGS,
                "secret_key is required when Langfuse is enabled",
            )

        self._settings.set(_KEY_ENABLED, "true" if enabled else "false")
        self._settings.set(_KEY_PUBLIC, public_key)
        self._settings.set(_KEY_HOST, host)
        if secret_key:
            token = self._write_fernet().encrypt(secret_key.encode("utf-8"))
            existing = self._secrets.get(_SECRET_KEY)
            if existing is not None:
                self._secrets.rotate(_SECRET_KEY, token)
            else:
                self._secrets.get_or_create(_SECRET_KEY, lambda: token)
        return self.load()

    async def test_connection(
        self,
        *,
        public_key: str | None = None,
        host: str | None = None,
        secret_key: str | None = None,
    ) -> dict[str, Any]:
        stored = self.load()
        pk = (public_key or stored.public_key).strip()
        h = (host or stored.host).strip().rstrip("/")
        sk = secret_key
        if sk is None:
            token = self._secrets.get(_SECRET_KEY)
            sk = self._decrypt(token) if token is not None else None
        if not pk or not h or not sk:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "Langfuse credentials are incomplete")

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, verify_langfuse_credentials, h, pk, sk)

    def harness_config(self) -> Any:
        """Build octop-harness ``LangfuseConfig`` for ``HarnessAgentManager``."""
        from octop_harness.observability.langfuse import LangfuseConfig  # noqa: PLC0415

        view = self.load()
        if not view.enabled:
            return LangfuseConfig(enabled=False)
        token = self._secrets.get(_SECRET_KEY)
        if not view.configured or token is None:
            return None
        return LangfuseConfig(
            enabled=True,
            public_key=view.public_key,
            host=view.host,
            secret_key=self._decrypt(token),
        )
