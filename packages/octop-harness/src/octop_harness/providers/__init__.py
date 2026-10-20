"""Core provider preset types and template loader.

``ModelPreset`` and ``ProviderPreset`` are the canonical dataclasses for
provider configuration presets used across octop-harness — both in the
library core and the CLI.

``load_provider_templates`` loads presets from JSON, with priority:
1. ``templates_path`` argument (explicit file, no fallback).
2. ``~/.octop-harness/providers_template.json`` (user-customisable).
3. Bundled ``providers/provider_template.json`` (fallback).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from octop_harness.providers.api import serialize_model_preset, serialize_provider_preset

_BUILTIN_PACKAGE = "octop_harness.providers"
_TEMPLATE_FILENAME = "provider_template.json"
_USER_DIR = Path.home() / ".octop-harness"

_INPUT_MODALITIES = frozenset({"text", "image", "audio", "video"})


@dataclass(frozen=True)
class ModelPreset:
    """A model available from a provider.

    Attributes:
        max_input_tokens: Maximum prompt/input tokens (0 = unknown).
        context_window: Total input + output context window (0 = unknown).
        max_output_tokens: Maximum generated/output tokens (0 = unknown).
        input: Modalities the model accepts (e.g. ``("text", "image")``).
        reasoning: When ``True``, the model is a reasoning / extended-thinking model.
    """

    id: str
    name: str
    max_input_tokens: int = 0
    input: tuple[str, ...] = ("text",)
    reasoning: bool = False
    context_window: int = 0
    max_output_tokens: int = 0

    def __post_init__(self) -> None:
        if self.max_input_tokens < 0 or self.context_window < 0 or self.max_output_tokens < 0:
            raise ValueError(f"ModelPreset({self.id}) token limits must be non-negative")
        if self.max_input_tokens <= 0 < self.context_window:
            object.__setattr__(self, "max_input_tokens", self.context_window)
        if self.context_window <= 0 < self.max_input_tokens:
            object.__setattr__(self, "context_window", self.max_input_tokens)

    @property
    def effective_context_window(self) -> int:
        """Return total context, preserving legacy max-input-only presets."""
        return self.context_window or self.max_input_tokens

    @property
    def is_multimodal(self) -> bool:
        """True when the model accepts non-text modalities."""
        return any(modality != "text" for modality in self.input)


@dataclass(frozen=True)
class ProviderPreset:
    """Configuration preset for an LLM provider.

    Each preset row is one site (one ``base_url``). Optional ``vendor`` groups
    multiple sites for dashboard UIs (CN / intl / coding plan, etc.).

    Attributes:
        logo: Filename of the bundled logo in ``octop_harness.providers.logos``
            (e.g. ``"openai.png"``). Empty string means no built-in logo.
            Access the bytes via
            ``importlib.resources.files("octop_harness.providers.logos").joinpath(preset.logo).read_bytes()``.
        vendor: Brand grouping key shared by related site presets.
        vendor_name: Human-readable brand label for grouped UIs.
        variant: Site/plan discriminator within a vendor (e.g. ``open_platform_cn``).
    """

    id: str
    name: str
    base_url: str
    protocol: str = "openai"
    api_key_env: str = ""
    api_key_prefix: str = ""
    models: list[ModelPreset] = field(default_factory=list)
    logo: str = ""
    vendor: str = ""
    vendor_name: str = ""
    variant: str = ""


def _parse_model_input(raw: object, *, model_id: str = "") -> tuple[str, ...]:
    """Normalise a model ``input`` field from JSON into a modality tuple."""
    if not isinstance(raw, list) or not raw:
        return ("text",)
    out: list[str] = []
    for item in raw:
        modality = str(item)
        if modality not in _INPUT_MODALITIES:
            suffix = f" for model {model_id!r}" if model_id else ""
            allowed = ", ".join(sorted(_INPUT_MODALITIES))
            raise ValueError(f"invalid input modality {modality!r}{suffix}; expected one of: {allowed}")
        out.append(modality)
    return tuple(out)


def _parse_model_reasoning(raw: object) -> bool:
    """Normalise a model ``reasoning`` field from JSON."""
    return raw is True


def _parse_presets(data: list[dict[str, object]]) -> list[ProviderPreset]:
    """Deserialise a list of provider dicts into ProviderPreset objects."""
    out: list[ProviderPreset] = []
    for i, item in enumerate(data):
        try:
            raw_models = item.get("models", [])
            models = []
            for m in raw_models if isinstance(raw_models, list) else []:
                if not isinstance(m, dict):
                    raise ValueError("models entries must be JSON objects")
                max_input = int(m.get("max_input_tokens", 0))
                context_window = int(m.get("context_window", 0))
                if max_input <= 0:
                    max_input = context_window
                if context_window <= 0:
                    context_window = max_input
                models.append(
                    ModelPreset(
                        id=str(m["id"]),
                        name=str(m["name"]),
                        max_input_tokens=max_input,
                        input=_parse_model_input(m.get("input"), model_id=str(m["id"])),
                        reasoning=_parse_model_reasoning(m.get("reasoning")),
                        context_window=context_window,
                        max_output_tokens=int(m.get("max_output_tokens", 0)),
                    )
                )
            out.append(
                ProviderPreset(
                    id=str(item["id"]),
                    name=str(item["name"]),
                    base_url=str(item["base_url"]),
                    protocol=str(item.get("protocol", "openai")),
                    api_key_env=str(item.get("api_key_env", "")),
                    api_key_prefix=str(item.get("api_key_prefix", "")),
                    models=models,
                    logo=str(item.get("logo", "")),
                    vendor=str(item.get("vendor", "")),
                    vendor_name=str(item.get("vendor_name", "")),
                    variant=str(item.get("variant", "")),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid provider preset at index {i}: {exc}") from exc
    return out


def load_provider_templates(
    templates_path: str | Path | None = None,
    *,
    _user_dir: Path | None = None,
) -> list[ProviderPreset]:
    """Load provider presets from JSON.

    Priority:
    1. ``templates_path`` (explicit path; raises ``FileNotFoundError`` if missing).
    2. ``~/.octop-harness/providers_template.json`` (user-customisable).
    3. Bundled ``providers/provider_template.json`` (fallback).

    Args:
        templates_path: Path to a custom JSON file in the same format as
            ``provider_template.json``. When supplied, this file is loaded
            directly with no fallback.
        _user_dir: Override the user home directory (for tests only).

    Returns:
        List of :class:`ProviderPreset`.

    Raises:
        FileNotFoundError: If ``templates_path`` is given but does not exist.
        ValueError: If the JSON file cannot be parsed as a list of provider dicts.
    """
    if templates_path is not None:
        p = Path(templates_path)
        if not p.exists():
            raise FileNotFoundError(f"Provider templates file not found: {p}")
        try:
            data: list[dict[str, object]] = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in provider templates file {p}: {exc}") from exc
        if not isinstance(data, list):
            raise ValueError(f"Expected a JSON array in provider templates file {p}, got {type(data).__name__}")
        return _parse_presets(data)

    resolved_user = (_user_dir or _USER_DIR) / "providers_template.json"
    if resolved_user.exists():
        try:
            user_data: list[dict[str, object]] = json.loads(resolved_user.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in user providers_template.json ({resolved_user}): {exc}") from exc
        if not isinstance(user_data, list):
            raise ValueError(
                f"Expected a JSON array in user providers_template.json"
                f" ({resolved_user}), got {type(user_data).__name__}"
            )
        return _parse_presets(user_data)

    # Fallback: bundled JSON
    pkg = resources.files(_BUILTIN_PACKAGE)
    raw = pkg.joinpath(_TEMPLATE_FILENAME).read_text(encoding="utf-8")
    try:
        bundled_data: list[dict[str, object]] = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in bundled provider_template.json: {exc}") from exc
    if not isinstance(bundled_data, list):
        raise ValueError(f"Expected a JSON array in bundled provider_template.json, got {type(bundled_data).__name__}")
    return _parse_presets(bundled_data)


__all__ = [
    "ModelPreset",
    "ProviderPreset",
    "load_provider_templates",
    "serialize_model_preset",
    "serialize_provider_preset",
]
