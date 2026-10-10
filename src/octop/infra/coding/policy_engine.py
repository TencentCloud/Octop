"""Data-driven permission policy engine for Code Console (S6).

Before the ACP runner executes a tool call, the console evaluates it against
a policy matrix. The result is one of ``allow`` / ``deny`` / ``ask``.
``ask`` surfaces a permission card to the user; ``deny`` rejects the call
outright; ``allow`` passes it through.

Policies are stored as JSON in the settings table (key
``coding_policy:user:<id>``) and fall back to a safe built-in default matrix
when no override exists.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# tool_kind taxonomy used by the harness permission system.
DEFAULT_POLICY: dict[str, str] = {
    # reads — always safe
    "read_file": "allow",
    "list_dir": "allow",
    "search": "allow",
    "view": "allow",
    "inspect": "allow",
    # writes — require human approval
    "edit": "ask",
    "write": "ask",
    "create": "ask",
    "rename": "ask",
    # destructive — deny by default
    "delete": "deny",
    "remove": "deny",
    # execution — require approval
    "run_command": "ask",
    "shell": "ask",
    "execute": "ask",
    # network — require approval
    "web_fetch": "ask",
    "http": "ask",
    "network": "ask",
}


def _normalize_kind(tool_kind: str, tool_name: str) -> str:
    k = (tool_kind or "").lower().strip()
    if k:
        return k
    # Fall back to inferring from the tool name.
    n = (tool_name or "").lower()
    for prefix, kind in (
        ("read", "read_file"),
        ("write", "write"),
        ("edit", "edit"),
        ("delete", "delete"),
        ("remove", "delete"),
        ("run", "run_command"),
        ("exec", "execute"),
        ("list", "list_dir"),
        ("search", "search"),
        ("fetch", "web_fetch"),
    ):
        if n.startswith(prefix):
            return kind
    return "ask"


class PolicyEngine:
    def __init__(self, settings_repo: Any, user_id: int) -> None:
        self._settings = settings_repo
        self._user_id = user_id
        self._matrix: dict[str, str] | None = None

    def _load_matrix(self) -> dict[str, str]:
        if self._matrix is not None:
            return self._matrix
        matrix = dict(DEFAULT_POLICY)
        try:
            raw = self._settings.get(f"coding_policy:user:{self._user_id}")
            if raw:
                data = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(data, dict):
                    for k, v in data.items():
                        if v in ("allow", "deny", "ask"):
                            matrix[str(k).lower()] = v
        except Exception:  # noqa: BLE001
            logger.exception("failed to load coding policy for user %s", self._user_id)
        self._matrix = matrix
        return matrix

    def reload(self) -> None:
        self._matrix = None

    def evaluate(self, *, tool_name: str, tool_kind: str, payload: Any = None) -> dict[str, Any]:
        """Return ``{action, reason, tool_kind}`` for a tool call."""
        kind = _normalize_kind(tool_kind, tool_name)
        matrix = self._load_matrix()
        action = matrix.get(kind, "ask")
        if action not in ("allow", "deny", "ask"):
            action = "ask"
        reason = {
            "allow": f"tool '{tool_name}' ({kind}) is allowed by policy",
            "deny": f"tool '{tool_name}' ({kind}) is denied by policy",
            "ask": f"tool '{tool_name}' ({kind}) requires approval",
        }[action]
        return {"action": action, "reason": reason, "tool_kind": kind}

    def matrix(self) -> dict[str, str]:
        return dict(self._load_matrix())
