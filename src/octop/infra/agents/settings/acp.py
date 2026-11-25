"""User-scoped global ACP runner configuration (settings table)."""

from __future__ import annotations

import json
import logging
import shutil
import sys
from pathlib import Path
from typing import Any

from octop_harness.acp.models import ACPConfig, default_acp_runners

from octop.infra.db.repos.agents import AgentRepo, AgentRow
from octop.infra.db.repos.settings import SettingsRepo

logger = logging.getLogger(__name__)


def host_runner_argv(command: str, args: list[str], env: dict[str, str]) -> tuple[str, list[str]]:
    """Launch Windows npm's npx entry point directly with Node and no command shell."""
    if sys.platform != "win32" or Path(command).name.lower() not in {"npx", "npx.cmd"}:
        return command, args
    shim = shutil.which(command, path=env.get("PATH"))
    if shim and Path(shim).suffix.lower() == ".cmd":
        root = Path(shim).parent
        script = root / "node_modules" / "npm" / "bin" / "npx-cli.js"
        node = shutil.which("node", path=env.get("PATH"))
        if node and script.is_file():
            return node, [str(script), *args]
    return command, args


def runtime_acp_config(runners: dict[str, Any]) -> ACPConfig:
    config = ACPConfig.from_dict({"runners": runners})
    for runner in config.runners.values():
        if runner.enabled:
            runner.command, runner.args = host_runner_argv(runner.command, runner.args, runner.env)
    return config


_SETTINGS_PREFIX = "acp_runners:user:"
# Until octop-harness ships these builtins, merge Octop-side defaults.
_OCTOP_BUILTIN_RUNNERS: dict[str, dict[str, Any]] = {
    "kimi_code": {
        "command": "kimi",
        "args": ["acp"],
        "trusted": True,
        "tool_parse_mode": "update_detail",
    },
    "cursor_cli": {
        "command": "agent",
        "args": ["acp"],
        "trusted": True,
        "tool_parse_mode": "update_detail",
    },
    "pi": {
        "command": "npx",
        "args": ["-y", "pi-acp"],
        "trusted": True,
        "tool_parse_mode": "update_detail",
    },
}


def _settings_key(user_id: int) -> str:
    return f"{_SETTINGS_PREFIX}{user_id}"


class ACPSettingsStore:
    """Persist ACP runner definitions once per user; agents only store ``tool_enabled``."""

    def __init__(self, *, settings_repo: SettingsRepo, agents_repo: AgentRepo) -> None:
        self._settings = settings_repo
        self._agents = agents_repo

    def load_runners(self, user_id: int) -> dict[str, Any]:
        """Return merged runner dict (built-ins + saved overrides)."""
        raw = self._settings.get(_settings_key(user_id))
        if raw:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("invalid acp_runners JSON for user %s; using defaults", user_id)
                data = {}
            if isinstance(data, dict):
                runners_raw = data.get("runners")
                if isinstance(runners_raw, dict):
                    return _runners_response(runners_raw)
                return _runners_response(data)

        migrated = self._migrate_legacy_from_agents(user_id)
        if migrated is not None:
            self._save_raw_runners(user_id, migrated)
            return _runners_response(migrated)

        return _runners_response({})

    def save_runners(self, user_id: int, runners: dict[str, Any]) -> dict[str, Any]:
        self._save_raw_runners(user_id, runners)
        return self.load_runners(user_id)

    def _save_raw_runners(self, user_id: int, runners: dict[str, Any]) -> None:
        self._settings.set(
            _settings_key(user_id), json.dumps({"runners": runners}, ensure_ascii=False)
        )

    def _migrate_legacy_from_agents(self, user_id: int) -> dict[str, Any] | None:
        best: dict[str, Any] | None = None
        best_score = -1
        touched: list[AgentRow] = []
        for row in self._agents.list_by_user(user_id):
            cfg = _parse_config_json(row.config_json)
            acp = cfg.get("acp")
            if not isinstance(acp, dict):
                continue
            legacy = acp.get("runners")
            if not isinstance(legacy, dict) or not legacy:
                continue
            touched.append(row)
            score = sum(1 for v in legacy.values() if isinstance(v, dict) and v.get("enabled"))
            if score > best_score or (score == best_score and len(legacy) > len(best or {})):
                best = legacy
                best_score = score
        if best is None:
            return None
        logger.info("migrated legacy per-agent ACP runners to global settings for user %s", user_id)
        self._strip_legacy_runners(touched)
        return best

    def _strip_legacy_runners(self, rows: list[AgentRow]) -> None:
        for row in rows:
            cfg = _parse_config_json(row.config_json)
            acp = cfg.get("acp")
            if not isinstance(acp, dict) or "runners" not in acp:
                continue
            slim = {k: v for k, v in acp.items() if k != "runners"}
            if slim:
                cfg["acp"] = slim
            else:
                cfg.pop("acp", None)
            self._agents.update_config(
                row.agent_id, config_json=json.dumps(cfg, ensure_ascii=False)
            )


def _runners_response(raw_runners: dict[str, Any]) -> dict[str, Any]:
    merged_raw = dict(raw_runners)
    harness_names = set(default_acp_runners())
    for name, spec in _OCTOP_BUILTIN_RUNNERS.items():
        if name not in harness_names and name not in merged_raw:
            merged_raw[name] = spec
    merged = ACPConfig.from_dict({"runners": merged_raw})
    return {name: runner.to_dict() for name, runner in merged.runners.items()}


def _parse_config_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}
