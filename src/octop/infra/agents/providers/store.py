"""Read Octop DB provider rows and build harness ``ProviderConfig`` objects."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

from harness_agent.config import ModelConfig, ProviderConfig

from octop.infra.agents.providers.model_flags import is_chat_eligible_model
from octop.infra.agents.providers.reasoning import reasoning_capability

if TYPE_CHECKING:
    from octop.infra.db.repos.agents import AgentRow
    from octop.infra.db.repos.providers import ProviderRepo

KIND_TO_PROTOCOL: dict[str, str] = {
    "openai": "openai",
    "anthropic": "anthropic",
    "ollama": "openai",
    "azure": "openai",
    "gemini": "openai",
}


def _infer_model_input_modalities(
    model_id: str,
    explicit: list[str] | None = None,
) -> list[str]:
    """Merge stored ``input`` with id-based heuristics (vision/audio)."""
    lower = model_id.lower()
    inputs: set[str] = set(explicit or ["text"])
    inputs.add("text")
    if (
        "-vl" in lower
        or "vision" in lower
        or "-image" in lower
        or "gpt-4o" in lower
        or "gpt-4.1" in lower
        or "claude-3" in lower
        or "gemini" in lower
    ):
        inputs.add("image")
    if "audio" in lower or "whisper" in lower:
        inputs.add("audio")
    return sorted(inputs)


def _model_dict_supports_image(model: dict[str, Any]) -> bool:
    model_id = str(model.get("id") or "")
    raw = model.get("input")
    explicit = list(raw) if isinstance(raw, list) else None
    return "image" in _infer_model_input_modalities(model_id, explicit)


def enabled_model_refs(
    provider_name: str,
    models: list[dict[str, Any]],
    *,
    provider_api_key: str | None = None,
) -> set[str]:
    """Return ``provider/model`` refs for chat-eligible enabled entries."""
    refs: set[str] = set()
    for model in models:
        if not is_chat_eligible_model(
            model, provider_name=provider_name, provider_api_key=provider_api_key
        ):
            continue
        model_id = str(model.get("id") or "").strip()
        refs.add(f"{provider_name}/{model_id}")
    return refs


def clear_stale_pins_for_provider(
    *,
    agent_repo: Any,
    settings_repo: Any,
    provider_name: str,
    models: list[dict[str, Any]],
) -> list[str]:
    """Clear agent / active-model pins for *provider_name* missing from *models*.

    One pass over agents. Returns cleared agent ids. Covers models removed in the
    current patch and pins left stale by earlier deletes.
    """
    valid = enabled_model_refs(provider_name, models)
    prefix = f"{provider_name}/"
    cleared: list[str] = []
    for row in agent_repo.list_all():
        dm = (row.default_model or "").strip()
        if not dm.startswith(prefix) or dm in valid:
            continue
        agent_repo.update_config(row.agent_id, default_model=None)
        cleared.append(row.agent_id)
    active_name, active_model = settings_repo.get_active_model()
    if active_name == provider_name and active_model:
        ref = f"{active_name}/{active_model}"
        if ref not in valid:
            settings_repo.delete("active_model")
    return cleared


class ProviderStore:
    """Maps persisted provider rows to harness runtime provider configs."""

    def __init__(
        self,
        provider_repo: ProviderRepo,
    ) -> None:
        self._provider_repo = provider_repo

    def iter_usable_rows(self) -> Iterator[Any]:
        """Yield enabled DB providers that have credentials and at least one enabled model."""
        for row in self._provider_repo.list_all():
            if not row.enabled:
                continue
            if not row.base_url or not row.api_key:
                continue
            models = row.get_models()
            if not models:
                continue
            if any(
                is_chat_eligible_model(m, provider_name=row.name, provider_api_key=row.api_key)
                for m in models
            ):
                yield row

    def has_usable_providers(self) -> bool:
        """True when at least one enabled provider has credentials and a model."""
        return next(self.iter_usable_rows(), None) is not None

    def build_harness_configs(self) -> list[ProviderConfig]:
        out: list[ProviderConfig] = []
        for row in self.iter_usable_rows():
            protocol = KIND_TO_PROTOCOL.get(row.kind, "openai")
            raw_models = json.loads(row.models_json) if getattr(row, "models_json", None) else []
            models = [
                self._model_config_from_row(m)
                for m in raw_models
                if is_chat_eligible_model(m, provider_name=row.name, provider_api_key=row.api_key)
            ]
            if not models:
                continue
            headers: dict[str, str] = {}
            if row.extra_json:
                try:
                    extra = json.loads(row.extra_json)
                    if isinstance(extra, dict) and isinstance(extra.get("headers"), dict):
                        headers = {str(k): str(v) for k, v in extra["headers"].items()}
                except Exception:
                    pass
            out.append(
                ProviderConfig(
                    id=row.name,
                    base_url=row.base_url,
                    api_key=row.api_key,
                    protocol=protocol,  # type: ignore[arg-type]
                    name=row.name,
                    models=models,
                    headers=headers,
                )
            )
        return out

    @staticmethod
    def _model_config_from_row(raw: dict[str, object]) -> ModelConfig:
        data = dict(raw)
        model_id = str(data.get("id") or "")
        explicit = data.get("input")
        inputs = list(explicit) if isinstance(explicit, list) else ["text"]
        data["input"] = _infer_model_input_modalities(model_id, inputs)
        # Octop catalogs store ``context_window``; harness ModelConfig uses
        # ``max_input_tokens`` (drives UI breakdown cap + summarization profile).
        if not data.get("max_input_tokens") and data.get("context_window"):
            data["max_input_tokens"] = data["context_window"]
        return ModelConfig.from_dict(data)

    def is_model_ref_multimodal(self, ref: str) -> bool:
        """True when *ref* resolves to a model that accepts images."""
        ref = ref.strip()
        if not ref or "/" not in ref:
            return False
        provider_name, _, model_id = ref.partition("/")
        row = self._provider_repo.get_by_name(provider_name)
        if row is None:
            return False
        for model in row.get_models():
            if model.get("id") == model_id and is_chat_eligible_model(
                model, provider_name=provider_name, provider_api_key=row.api_key
            ):
                return _model_dict_supports_image(model)
        return False

    def resolve_multimodal_model_ref(self) -> str | None:
        """First enabled image-capable model across usable providers."""
        for row in self.iter_usable_rows():
            for model in row.get_models():
                if not is_chat_eligible_model(
                    model, provider_name=row.name, provider_api_key=row.api_key
                ):
                    continue
                if _model_dict_supports_image(model):
                    return f"{row.name}/{model['id']}"
        return None

    def resolve_model_for_multimodal_turn(
        self,
        model_ref: str | None,
        *,
        needs_multimodal: bool,
    ) -> str | None:
        """Keep explicit ref when it supports vision; else upgrade to a vision model."""
        if not needs_multimodal:
            return model_ref
        ref = (model_ref or "").strip() or None
        if ref and self.is_model_ref_multimodal(ref):
            return ref
        upgraded = self.resolve_multimodal_model_ref()
        return upgraded or ref

    def resolve_first_model_ref(self) -> str | None:
        """First chat-eligible enabled model across usable providers."""
        for row in self.iter_usable_rows():
            for model in row.get_models():
                if not is_chat_eligible_model(
                    model, provider_name=row.name, provider_api_key=row.api_key
                ):
                    continue
                model_id = str(model.get("id") or "").strip()
                if model_id:
                    return f"{row.name}/{model_id}"
        return None

    def is_model_ref_usable(self, ref: str) -> bool:
        """Return True when *ref* points at a chat-eligible model on a usable provider."""
        ref = ref.strip()
        if not ref or ref.lower() == "auto" or "/" not in ref:
            return False
        provider_name, _, model_id = ref.partition("/")
        if not provider_name or not model_id:
            return False
        row = self._provider_repo.get_by_name(provider_name)
        if row is None or not row.enabled or not row.api_key or not row.base_url:
            return False
        for model in row.get_models():
            if model.get("id") != model_id:
                continue
            return is_chat_eligible_model(
                model, provider_name=provider_name, provider_api_key=row.api_key
            )
        return False

    def get_model_reasoning_capability(self, ref: str) -> dict[str, Any] | None:
        """Return normalized reasoning metadata for a usable model ref."""
        if not self.is_model_ref_usable(ref):
            return None
        provider_name, _, model_id = ref.partition("/")
        row = self._provider_repo.get_by_name(provider_name)
        if row is None:
            return None
        for model in row.get_models():
            if model.get("id") == model_id and model.get("enabled", True):
                return reasoning_capability(model, base_url=row.base_url)
        return None

    def resolve_explicit_default_model(
        self,
        row: AgentRow,
        cfg: dict[str, Any],
    ) -> str | None:
        """Pinned expert default when set and usable; otherwise ``None`` (AUTO)."""
        for candidate in (row.default_model, cfg.get("default_model")):
            if not isinstance(candidate, str):
                continue
            ref = candidate.strip()
            if ref and ref.lower() != "auto" and self.is_model_ref_usable(ref):
                return ref
        return None

    def find_agents_using_provider(
        self,
        *,
        agent_repo: Any,
        get_config: Callable[[str], dict[str, Any]],
        provider_name: str,
    ) -> list[dict[str, str]]:
        """Return agents referencing *provider_name* in config or default_model."""
        refs: list[dict[str, str]] = []
        prefix = f"{provider_name}/"
        for row in agent_repo.list_all():
            cfg = get_config(row.agent_id)
            if provider_name in (cfg.get("providers") or []):
                refs.append({"agent_id": row.agent_id, "name": row.name})
                continue
            if row.default_model and (
                row.default_model == provider_name or row.default_model.startswith(prefix)
            ):
                refs.append({"agent_id": row.agent_id, "name": row.name})
        return refs


__all__ = [
    "KIND_TO_PROTOCOL",
    "ProviderStore",
    "clear_stale_pins_for_provider",
    "enabled_model_refs",
]
