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

from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)

_KEY_ENABLED = "observability_langfuse_enabled"
_KEY_PUBLIC = "observability_langfuse_public_key"
_KEY_HOST = "observability_langfuse_host"
_SECRET_KEY = "langfuse_secret_key"


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
            encoded = secret_key.encode("utf-8")
            existing = self._secrets.get(_SECRET_KEY)
            if existing is not None:
                self._secrets.rotate(_SECRET_KEY, encoded)
            else:
                self._secrets.get_or_create(_SECRET_KEY, lambda: encoded)
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
            raw = self._secrets.get(_SECRET_KEY)
            sk = raw.decode("utf-8") if raw else None
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
        raw = self._secrets.get(_SECRET_KEY)
        if not view.configured or raw is None:
            return None
        return LangfuseConfig(
            enabled=True,
            public_key=view.public_key,
            host=view.host,
            secret_key=raw.decode("utf-8"),
        )
