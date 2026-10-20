"""CLI-layer agent manager: file persistence + library HarnessAgentManager delegation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from octop_harness import HarnessAgentManager
from octop_harness.cli.agents.profile import AgentProfile


class CliAgentManager:
    """Manages agent profiles on disk and delegates runtime ops to HarnessAgentManager.

    Profiles are stored in ``config.json`` under the ``agents`` key.
    Runtime streaming and cancellation go through the library HarnessAgentManager.
    """

    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path
        self._runtime = HarnessAgentManager()

    def _load(self) -> dict[str, Any]:
        if not self._config_path.is_file():
            return {}
        try:
            return dict(json.loads(self._config_path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: dict[str, Any]) -> None:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    @property
    def default_agent_name(self) -> str:
        data = self._load()
        return str(data.get("default_agent", "main"))

    def list(self) -> list[AgentProfile]:
        data = self._load()
        agents_dict = data.get("agents")
        if not agents_dict:
            return [self._implicit_main(data)]
        return [AgentProfile.from_dict(name, cfg) for name, cfg in agents_dict.items()]

    def get(self, name: str) -> AgentProfile | None:
        data = self._load()
        agents_dict = data.get("agents")
        if not agents_dict:
            if name == "main":
                return self._implicit_main(data)
            return None
        if name not in agents_dict:
            return None
        return AgentProfile.from_dict(name, agents_dict[name])

    def create(self, profile: AgentProfile) -> None:
        data = self._load()
        agents_dict: dict[str, Any] = data.setdefault("agents", {})
        if profile.name in agents_dict:
            raise ValueError(f"Agent '{profile.name}' already exists")
        agents_dict[profile.name] = profile.to_dict()
        self._save(data)

    def remove(self, name: str) -> None:
        if name == "main":
            raise ValueError("cannot remove 'main' agent (it is required)")
        data = self._load()
        agents_dict = data.get("agents", {})
        if name not in agents_dict:
            raise ValueError(f"Agent '{name}' not found")
        del agents_dict[name]
        if data.get("default_agent") == name:
            data["default_agent"] = "main"
        self._save(data)

    def set_default(self, name: str) -> None:
        data = self._load()
        agents_dict = data.get("agents", {})
        if name not in agents_dict:
            raise ValueError(f"Agent '{name}' not found")
        data["default_agent"] = name
        self._save(data)

    def resolve(self, name: str) -> dict[str, Any]:
        """Return merged config dict for *name* (profile overrides top-level)."""
        data = self._load()
        profile = self.get(name)
        if profile is None:
            raise ValueError(f"Agent '{name}' not found")
        top_level = {k: v for k, v in data.items() if k not in ("agents", "default_agent", "cli")}
        return profile.resolve(top_level)

    @property
    def runtime(self) -> HarnessAgentManager:
        """The underlying library HarnessAgentManager for streaming/cancel."""
        return self._runtime

    @staticmethod
    def _implicit_main(data: dict[str, Any]) -> AgentProfile:
        default_model = str(data.get("default_model", ""))
        provider = ""
        model = ""
        if "/" in default_model:
            provider, _, model = default_model.partition("/")
        return AgentProfile(name="main", provider=provider or None, model=model or None)
