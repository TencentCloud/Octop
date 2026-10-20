"""AgentProfile — named agent configuration with inheritance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AgentProfile:
    """A named agent profile with optional field overrides.

    Fields set to None inherit from the top-level config.
    """

    name: str
    provider: str | None = None
    model: str | None = None
    backend: str | dict[str, object] | None = None
    workspace_dir: str | None = None

    def resolve(self, top_level: dict[str, Any]) -> dict[str, Any]:
        """Merge this profile with top-level config to produce a full agent config dict.

        The returned dict is suitable for HarnessAgentConfig.from_dict().
        Profile fields override top-level; unset fields inherit.
        """
        resolved = dict(top_level)

        if self.provider and self.model:
            resolved["default_model"] = f"{self.provider}/{self.model}"
        elif self.provider:
            provider_cfg = resolved.get("providers", {}).get(self.provider, {})
            models = provider_cfg.get("models", [])
            if models:
                first_id = models[0]["id"] if isinstance(models[0], dict) else models[0].id
                resolved["default_model"] = f"{self.provider}/{first_id}"

        if self.backend is not None:
            resolved["backend"] = self.backend
        if self.workspace_dir is not None:
            resolved["workspace_dir"] = self.workspace_dir

        return resolved

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict (only non-None fields)."""
        d: dict[str, Any] = {}
        if self.provider is not None:
            d["provider"] = self.provider
        if self.model is not None:
            d["model"] = self.model
        if self.backend is not None:
            d["backend"] = self.backend
        if self.workspace_dir is not None:
            d["workspace_dir"] = self.workspace_dir
        return d

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> AgentProfile:
        """Construct from a config dict entry."""
        return cls(
            name=name,
            provider=data.get("provider"),
            model=data.get("model"),
            backend=data.get("backend"),
            workspace_dir=data.get("workspace_dir"),
        )
