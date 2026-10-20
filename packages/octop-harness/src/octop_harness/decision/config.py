"""Declarative settings for the decision-model middleware.

The middleware is mounted only when :func:`decision_active` is true. A missing
or disabled config leaves the agent chain unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

DecisionProvider = Literal["laya", "jev", "microsoft", "custom"]
_PROVIDERS: frozenset[str] = frozenset({"laya", "jev", "microsoft", "custom"})


@dataclass
class DecisionConfig:
    """How to call a yes/no decision model before a chat turn.

    ``api_key`` is injected by the host at runtime and is omitted from
    :meth:`to_dict`.
    """

    enabled: bool = False
    provider: DecisionProvider = "laya"
    endpoint: str = ""
    api_key: str = field(default="", repr=False, compare=False)
    model: str = ""
    skills: bool = True
    tools: bool = True
    team: bool = True
    threshold: float = 0.6
    tool_min_count: int = 8
    max_selected: int = 8

    def __post_init__(self) -> None:
        provider = str(self.provider).strip().lower()
        if provider not in _PROVIDERS:
            raise ValueError(f"decision provider must be one of {sorted(_PROVIDERS)}")
        self.provider = provider  # type: ignore[assignment]
        self.endpoint = str(self.endpoint or "").strip()
        self.model = str(self.model or "").strip()
        if not 0 < float(self.threshold) < 1:
            raise ValueError("decision threshold must be between 0 and 1")
        if int(self.tool_min_count) < 1:
            raise ValueError("decision tool_min_count must be at least 1")
        if int(self.max_selected) < 1:
            raise ValueError("decision max_selected must be at least 1")
        self.tool_min_count = int(self.tool_min_count)
        self.max_selected = int(self.max_selected)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "endpoint": self.endpoint,
            "model": self.model,
            "skills": self.skills,
            "tools": self.tools,
            "team": self.team,
            "threshold": self.threshold,
            "tool_min_count": self.tool_min_count,
            "max_selected": self.max_selected,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DecisionConfig:
        if not isinstance(data, dict):
            raise TypeError(f"DecisionConfig.from_dict expected a dict, got {type(data).__name__}")
        return cls(
            enabled=bool(data.get("enabled", False)),
            provider=data.get("provider") or "laya",
            endpoint=str(data.get("endpoint") or ""),
            model=str(data.get("model") or ""),
            skills=bool(data.get("skills", True)),
            tools=bool(data.get("tools", True)),
            team=bool(data.get("team", True)),
            threshold=float(data.get("threshold", 0.6)),
            tool_min_count=int(data.get("tool_min_count", 8)),
            max_selected=int(data.get("max_selected", 8)),
        )


def decision_active(decision: DecisionConfig | None) -> bool:
    """True when the middleware should be mounted."""
    if decision is None or not decision.enabled:
        return False
    if not decision.endpoint:
        return False
    return bool(decision.skills or decision.tools or decision.team)
