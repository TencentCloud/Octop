"""Global decision-model settings passed into harness."""

from __future__ import annotations

import json
from dataclasses import dataclass

from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.errors import ErrorCode, OctopError

_SETTINGS_KEY = "decision_model"
_SECRET_KEY = "decision_api_key"
_PROVIDER_ORDER = ("jev", "microsoft", "laya", "custom")
_PROVIDERS = frozenset(_PROVIDER_ORDER)


@dataclass(frozen=True)
class DecisionServiceConfig:
    provider: str
    endpoint: str
    model: str
    api_key_set: bool


@dataclass(frozen=True)
class DecisionSettings:
    enabled: bool
    provider: str
    services: tuple[DecisionServiceConfig, ...]
    skills: bool
    tools: bool
    team: bool
    threshold: float
    tool_min_count: int
    legacy_key_owner: str = ""

    @property
    def endpoint(self) -> str:
        return self.selected.endpoint

    @property
    def model(self) -> str:
        return self.selected.model

    @property
    def api_key_set(self) -> bool:
        return self.selected.api_key_set

    @property
    def selected(self) -> DecisionServiceConfig:
        for item in self.services:
            if item.provider == self.provider:
                return item
        return self.services[0]

    @property
    def active(self) -> bool:
        return bool(self.enabled and self.endpoint and (self.skills or self.tools or self.team))


class DecisionSettingsStore:
    """Persist the decision-model switch. The secret never goes back to the UI."""

    def __init__(self, *, settings_repo: SettingsRepo, secret_repo: SecretRepo) -> None:
        self._settings = settings_repo
        self._secrets = secret_repo

    def load(self) -> DecisionSettings:
        raw = self._settings.get(_SETTINGS_KEY)
        data: dict[str, object] = {}
        if raw:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                data = parsed
        provider = str(data.get("provider") or "laya").strip().lower()
        if provider not in _PROVIDERS:
            provider = "laya"
        legacy_owner = "" if isinstance(data.get("services"), dict) else provider
        services = tuple(
            DecisionServiceConfig(
                provider=name,
                endpoint=item["endpoint"],
                model=item["model"],
                api_key_set=bool(self._stored_key(name, legacy_owner=legacy_owner)),
            )
            for name, item in _service_map(data, provider).items()
        )
        return DecisionSettings(
            enabled=bool(data.get("enabled", False)),
            provider=provider,
            services=services,
            skills=bool(data.get("skills", True)),
            tools=bool(data.get("tools", True)),
            team=bool(data.get("team", True)),
            threshold=_threshold(data.get("threshold", 0.6)),
            tool_min_count=_tool_min_count(data.get("tool_min_count", 8)),
            legacy_key_owner=legacy_owner,
        )

    def save(
        self,
        *,
        enabled: bool,
        provider: str,
        endpoint: str,
        model: str,
        skills: bool,
        tools: bool,
        team: bool,
        threshold: float,
        tool_min_count: int,
        api_key: str | None = None,
        services: list[dict[str, object]] | None = None,
    ) -> DecisionSettings:
        previous = self.load()
        provider = provider.strip().lower()
        if provider not in _PROVIDERS:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "unknown decision provider")
        if enabled and not (skills or tools or team):
            raise OctopError(
                ErrorCode.SLASH_BAD_ARGS,
                "enable at least one of skills, tools, or team",
            )
        if not 0 < float(threshold) < 1:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "threshold must be between 0 and 1")
        if int(tool_min_count) < 1:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "tool_min_count must be at least 1")
        self._migrate_legacy_key(previous.legacy_key_owner)
        current = {
            item.provider: {"endpoint": item.endpoint, "model": item.model}
            for item in previous.services
        }
        updates = (
            services
            if services is not None
            else [
                {
                    "provider": provider,
                    "endpoint": endpoint,
                    "model": model,
                    "api_key": api_key,
                }
            ]
        )
        for item in updates:
            name = str(item.get("provider") or "").strip().lower()
            if name not in _PROVIDERS:
                raise OctopError(ErrorCode.SLASH_BAD_ARGS, "unknown decision provider")
            next_endpoint = str(item.get("endpoint") or "").strip()
            next_model = str(item.get("model") or "").strip()
            _validate_service(
                name, next_endpoint, next_model, required=enabled and name == provider
            )
            previous_endpoint = current[name]["endpoint"]
            current[name] = {"endpoint": next_endpoint, "model": next_model}
            key = item.get("api_key", None)
            if isinstance(key, str):
                self._write_secret(name, key)
            elif previous_endpoint and previous_endpoint != next_endpoint:
                # Credentials belong to an endpoint. Forwarding the old secret
                # after an address change can leak it to another service.
                self._write_secret(name, "")
        selected = current[provider]
        payload = {
            "enabled": enabled,
            "provider": provider,
            "endpoint": selected["endpoint"],
            "model": selected["model"],
            "services": current,
            "skills": skills,
            "tools": tools,
            "team": team,
            "threshold": float(threshold),
            "tool_min_count": int(tool_min_count),
        }
        self._settings.set(_SETTINGS_KEY, json.dumps(payload, ensure_ascii=False))
        return self.load()

    def harness_config(self) -> object | None:
        """Build a harness ``DecisionConfig``, or ``None`` when the switch is off."""
        view = self.load()
        if not view.active:
            return None
        from octop_harness.decision.config import DecisionConfig

        return DecisionConfig(
            enabled=True,
            provider=view.provider,  # type: ignore[arg-type]
            endpoint=view.endpoint,
            api_key=self._stored_key(view.provider, legacy_owner=view.legacy_key_owner),
            model=view.model,
            skills=view.skills,
            tools=view.tools,
            team=view.team,
            threshold=view.threshold,
            tool_min_count=view.tool_min_count,
        )

    async def probe(
        self,
        *,
        endpoint: str | None,
        api_key: str | None,
        model: str | None,
        provider: str | None,
    ) -> dict[str, object]:
        view = self.load()
        target = (endpoint if endpoint is not None else view.endpoint).strip()
        if not target.startswith(("http://", "https://")):
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "decision endpoint is required")
        from octop_harness.decision.client import HttpDecisionClient

        saved_key = ""
        if api_key is None and (
            endpoint is None or any(item.endpoint == target for item in view.services)
        ):
            owner = next(
                (item.provider for item in view.services if item.endpoint == target),
                view.provider,
            )
            saved_key = self._stored_key(owner, legacy_owner=view.legacy_key_owner)
        probe_key = api_key if api_key is not None else saved_key
        client = HttpDecisionClient(
            endpoint=target,
            api_key=probe_key,
            model=(model if model is not None else view.model).strip(),
            provider=(provider or view.provider).strip(),
        )
        try:
            probabilities = await client.score_async(
                state="连接测试",
                statements=[("ping", "这是一次连接测试。")],
                strict=True,
            )
        except Exception as exc:
            detail = str(exc).strip() or exc.__class__.__name__
            return {"ok": False, "error": f"could not reach {target}: {detail[:240]}"}
        probability = probabilities.get("ping")
        if probability is None:
            return {"ok": False, "error": "no probability returned"}
        return {"ok": True, "probability": probability}

    def _stored_key(self, provider: str, *, legacy_owner: str) -> str:
        raw = self._secrets.get(_scoped_secret(provider))
        if raw is not None:
            return raw.decode("utf-8").strip()
        if provider != legacy_owner:
            return ""
        legacy = self._secrets.get(_SECRET_KEY)
        if not legacy:
            return ""
        return legacy.decode("utf-8").strip()

    def _migrate_legacy_key(self, owner: str) -> None:
        if not owner or self._secrets.get(_scoped_secret(owner)) is not None:
            return
        legacy = self._secrets.get(_SECRET_KEY)
        if legacy:
            self._write_secret(owner, legacy.decode("utf-8"))

    def _write_secret(self, provider: str, api_key: str) -> None:
        key = _scoped_secret(provider)
        encoded = api_key.strip().encode("utf-8")
        existing = self._secrets.get(key)
        if existing is not None:
            self._secrets.rotate(key, encoded)
            return
        self._secrets.get_or_create(key, lambda: encoded)


def _scoped_secret(provider: str) -> str:
    return f"{_SECRET_KEY}:{provider}"


def _service_map(data: dict[str, object], provider: str) -> dict[str, dict[str, str]]:
    services = {name: {"endpoint": "", "model": ""} for name in _PROVIDER_ORDER}
    raw = data.get("services")
    if isinstance(raw, dict):
        for name, item in raw.items():
            if name not in _PROVIDERS or not isinstance(item, dict):
                continue
            services[str(name)] = {
                "endpoint": str(item.get("endpoint") or "").strip(),
                "model": str(item.get("model") or "").strip(),
            }
        return services
    endpoint = str(data.get("endpoint") or "").strip()
    model = str(data.get("model") or "").strip()
    if endpoint or model:
        services[provider] = {"endpoint": endpoint, "model": model}
    return services


def _validate_service(provider: str, endpoint: str, model: str, *, required: bool) -> None:
    if endpoint and not endpoint.startswith(("http://", "https://")):
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "endpoint must start with http:// or https://")
    if not required:
        return
    if not endpoint.startswith(("http://", "https://")):
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            "endpoint is required when the decision model is enabled",
        )
    if provider in {"jev", "microsoft"} and not model.strip():
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            "model is required for this decision provider",
        )


def _threshold(value: object) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.6
    if not 0 < number < 1:
        return 0.6
    return number


def _tool_min_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return 8
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 8
    return number if number >= 1 else 8
