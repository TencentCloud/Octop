"""ACP configuration and error types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ACPToolParseMode = Literal["call_title", "update_detail", "call_detail"]

DEFAULT_STDIO_BUFFER_LIMIT_BYTES = 50 * 1024 * 1024

_BUILTIN_RUNNERS: dict[str, dict[str, Any]] = {
    "opencode": {
        "command": "opencode",
        "args": ["acp"],
        "trusted": True,
        "tool_parse_mode": "update_detail",
    },
    "codebuddy": {
        "command": "codebuddy",
        "args": ["--acp"],
        "trusted": True,
        "tool_parse_mode": "update_detail",
    },
    "qwen_code": {
        "command": "qwen",
        "args": ["--acp"],
        "trusted": True,
        "tool_parse_mode": "call_detail",
    },
    "claude_code": {
        "command": "npx",
        "args": ["-y", "@zed-industries/claude-agent-acp"],
        "trusted": True,
        "tool_parse_mode": "update_detail",
    },
    "codex": {
        "command": "npx",
        "args": ["-y", "@zed-industries/codex-acp"],
        "trusted": True,
        "tool_parse_mode": "call_detail",
    },
}


class ACPErrors(Exception):
    def __init__(self, message: str, *, runner: str | None = None) -> None:
        super().__init__(message)
        self.runner = runner


class ACPConfigurationError(ACPErrors):
    pass


class ACPTransportError(ACPErrors):
    pass


class ACPProtocolError(ACPErrors):
    pass


class ACPSessionError(ACPErrors):
    pass


@dataclass
class ACPRunnerConfig:
    enabled: bool = False
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    trusted: bool = False
    tool_parse_mode: ACPToolParseMode = "update_detail"
    stdio_buffer_limit_bytes: int = DEFAULT_STDIO_BUFFER_LIMIT_BYTES

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "command": self.command,
            "args": list(self.args),
            "env": dict(self.env),
            "trusted": self.trusted,
            "tool_parse_mode": self.tool_parse_mode,
            "stdio_buffer_limit_bytes": self.stdio_buffer_limit_bytes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ACPRunnerConfig:
        mode = str(data.get("tool_parse_mode") or "update_detail")
        if mode not in ("call_title", "update_detail", "call_detail"):
            raise ValueError(f"invalid tool_parse_mode: {mode!r}")
        return cls(
            enabled=bool(data.get("enabled", False)),
            command=str(data.get("command") or ""),
            args=[str(x) for x in (data.get("args") or [])],
            env={str(k): str(v) for k, v in dict(data.get("env") or {}).items()},
            trusted=bool(data.get("trusted", False)),
            tool_parse_mode=mode,  # type: ignore[arg-type]
            stdio_buffer_limit_bytes=int(
                data.get("stdio_buffer_limit_bytes") or DEFAULT_STDIO_BUFFER_LIMIT_BYTES,
            ),
        )


def default_acp_runners() -> dict[str, ACPRunnerConfig]:
    out: dict[str, ACPRunnerConfig] = {}
    for name, spec in _BUILTIN_RUNNERS.items():
        out[name] = ACPRunnerConfig(
            enabled=False,
            command=str(spec["command"]),
            args=list(spec["args"]),
            trusted=bool(spec.get("trusted", False)),
            tool_parse_mode=spec.get("tool_parse_mode", "update_detail"),
        )
    return out


@dataclass
class ACPConfig:
    runners: dict[str, ACPRunnerConfig] = field(default_factory=default_acp_runners)

    def __post_init__(self) -> None:
        for name, runner in default_acp_runners().items():
            if name not in self.runners:
                self.runners[name] = runner

    def to_dict(self) -> dict[str, Any]:
        return {"runners": {name: cfg.to_dict() for name, cfg in self.runners.items()}}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ACPConfig:
        if not data:
            return cls()
        raw = data.get("runners") or data.get("agents") or {}
        if not isinstance(raw, dict):
            return cls()
        runners = default_acp_runners()
        for name, item in raw.items():
            if isinstance(item, dict):
                runners[str(name)] = ACPRunnerConfig.from_dict(item)
        return cls(runners=runners)

    def enabled_runner_names(self) -> list[str]:
        return sorted(name for name, cfg in self.runners.items() if cfg.enabled)


@dataclass
class SuspendedPermission:
    payload: dict[str, Any]
    options: list[dict[str, Any]]
    runner: str
    tool_name: str
    tool_kind: str
    target: str | None = None
    action: str | None = None
    summary: str | None = None
    command: str | None = None
    paths: list[str] = field(default_factory=list)
    requires_user_confirmation: bool = True
