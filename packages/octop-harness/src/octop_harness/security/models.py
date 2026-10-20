"""Declarative security policy for octop-harness hosts.

``SecurityPolicy`` is the user-facing configuration object. Host applications
(Octop dashboard, CLI, etc.) persist ``to_dict()`` output and pass it back via
``from_dict()``. At agent construction time, :meth:`apply_to_config` expands
the policy into ``HarnessAgentConfig`` fields consumed by deepagents
(``interrupt_on``, ``permissions``, ``pii_*``).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal

from deepagents.middleware.filesystem import FilesystemPermission

from octop_harness.config import HarnessAgentConfig

DEFAULT_HITL_TOOLS: tuple[str, ...] = (
    "bash",
    "execute",
    "write_file",
    "edit_file",
    "delete",
)

DEFAULT_SENSITIVE_PATHS: tuple[str, ...] = (
    "/etc/**",
    "/root/**",
    "/var/run/**",
    "/home/*/.ssh/**",
    "/home/*/.aws/**",
    "/**/.env",
    "/**/id_rsa",
    "/**/id_rsa.pub",
)

DecisionType = Literal["approve", "edit", "reject", "respond"]
FilesystemOperation = Literal["read", "write"]
FilesystemMode = Literal["allow", "deny"]
PiiStrategy = Literal["block", "redact", "mask", "hash"]
SkillScanMode = Literal["off", "warn", "block"]
ToolGuardMode = Literal["block", "warn", "require_approval"]


@dataclass
class HitlPolicy:
    """Human-in-the-loop approval before selected tools execute."""

    enabled: bool = False
    tools: list[str] | Literal["default"] = "default"
    allowed_decisions: list[DecisionType] = field(default_factory=lambda: ["approve", "reject"])


@dataclass
class FilesystemRule:
    """A single filesystem access rule (first match wins)."""

    operations: list[FilesystemOperation] = field(default_factory=lambda: ["read", "write"])
    paths: list[str] = field(default_factory=list)
    mode: FilesystemMode = "deny"


@dataclass
class FilesystemPolicy:
    """Path-based allow/deny rules for built-in filesystem tools."""

    enabled: bool = True
    rules: list[FilesystemRule] = field(default_factory=list)


@dataclass
class PiiPolicy:
    """API-key and secret redaction applied by harness PIIMiddleware."""

    enabled: bool = True
    strategy: PiiStrategy = "mask"
    surfaces: tuple[Literal["input", "output", "tool_results"], ...] = (
        "input",
        "output",
        "tool_results",
    )


@dataclass
class SkillScanPolicy:
    """Static analysis mode for skill directories before install/load."""

    mode: SkillScanMode = "warn"


@dataclass
class ToolGuardPolicy:
    """Regex scan of shell tool parameters before execution."""

    enabled: bool = True
    mode: ToolGuardMode = "warn"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _choice(value: Any, allowed: tuple[str, ...], default: str) -> Any:
    return value if value in allowed else default


def _hitl_from_raw(hitl_raw: dict[str, Any]) -> HitlPolicy:
    tools_raw = hitl_raw.get("tools", "default")
    if tools_raw == "default":
        tools: list[str] | Literal["default"] = "default"
    elif isinstance(tools_raw, list):
        tools = [str(t) for t in tools_raw if str(t).strip()]
    else:
        tools = "default"
    allowed = hitl_raw.get("allowed_decisions") or ["approve", "reject"]
    decisions = [str(d) for d in allowed if str(d) in {"approve", "edit", "reject", "respond"}]
    return HitlPolicy(
        enabled=bool(hitl_raw.get("enabled", False)),
        tools=tools,
        allowed_decisions=decisions or ["approve", "reject"],  # type: ignore[arg-type]
    )


def _filesystem_rules_from_raw(fs_raw: dict[str, Any]) -> list[FilesystemRule]:
    rules: list[FilesystemRule] = []
    for item in fs_raw.get("rules") or []:
        if not isinstance(item, dict):
            continue
        raw_ops = item.get("operations") or ["read", "write"]
        ops: list[FilesystemOperation] = [o for o in raw_ops if o in ("read", "write")]
        paths = [str(p) for p in (item.get("paths") or []) if str(p).strip()]
        mode = item.get("mode", "deny")
        if mode not in ("allow", "deny") or not paths:
            continue
        rules.append(FilesystemRule(operations=ops or ["read", "write"], paths=paths, mode=mode))
    return rules


def _pii_from_raw(pii_raw: dict[str, Any]) -> PiiPolicy:
    strategy = _choice(pii_raw.get("strategy", "mask"), ("block", "redact", "mask", "hash"), "mask")
    surfaces_raw = pii_raw.get("surfaces") or ["input", "output", "tool_results"]
    surfaces = tuple(s for s in surfaces_raw if s in ("input", "output", "tool_results"))
    return PiiPolicy(
        enabled=bool(pii_raw.get("enabled", True)),
        strategy=strategy,
        surfaces=surfaces or ("input", "output", "tool_results"),
    )


@dataclass
class SecurityPolicy:
    """Top-level security configuration for a harness agent."""

    hitl: HitlPolicy = field(default_factory=HitlPolicy)
    filesystem: FilesystemPolicy = field(default_factory=FilesystemPolicy)
    pii: PiiPolicy = field(default_factory=PiiPolicy)
    skill_scan: SkillScanPolicy = field(default_factory=SkillScanPolicy)
    tool_guard: ToolGuardPolicy = field(default_factory=ToolGuardPolicy)

    @classmethod
    def defaults(cls) -> SecurityPolicy:
        """Return the recommended self-hosted defaults."""
        return cls(
            hitl=HitlPolicy(enabled=False, tools="default"),
            filesystem=FilesystemPolicy(
                enabled=True,
                rules=[
                    FilesystemRule(
                        operations=["read", "write"],
                        paths=list(DEFAULT_SENSITIVE_PATHS),
                        mode="deny",
                    )
                ],
            ),
            pii=PiiPolicy(),
            skill_scan=SkillScanPolicy(mode="warn"),
            tool_guard=ToolGuardPolicy(enabled=True, mode="warn"),
        )

    def to_dict(self) -> dict[str, Any]:
        hitl_tools: list[str] | str = "default" if self.hitl.tools == "default" else list(self.hitl.tools)
        return {
            "hitl": {
                "enabled": self.hitl.enabled,
                "tools": hitl_tools,
                "allowed_decisions": list(self.hitl.allowed_decisions),
            },
            "filesystem": {
                "enabled": self.filesystem.enabled,
                "rules": [
                    {
                        "operations": list(rule.operations),
                        "paths": list(rule.paths),
                        "mode": rule.mode,
                    }
                    for rule in self.filesystem.rules
                ],
            },
            "pii": {
                "enabled": self.pii.enabled,
                "strategy": self.pii.strategy,
                "surfaces": list(self.pii.surfaces),
            },
            "skill_scan": {"mode": self.skill_scan.mode},
            "tool_guard": {
                "enabled": self.tool_guard.enabled,
                "mode": self.tool_guard.mode,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SecurityPolicy:
        if not data:
            return cls.defaults()
        hitl_raw = _as_dict(data.get("hitl"))
        fs_raw = _as_dict(data.get("filesystem"))
        pii_raw = _as_dict(data.get("pii"))
        scan_raw = _as_dict(data.get("skill_scan"))
        tg_raw = _as_dict(data.get("tool_guard"))
        return cls(
            hitl=_hitl_from_raw(hitl_raw),
            filesystem=FilesystemPolicy(
                enabled=bool(fs_raw.get("enabled", True)),
                rules=_filesystem_rules_from_raw(fs_raw),
            ),
            pii=_pii_from_raw(pii_raw),
            skill_scan=SkillScanPolicy(mode=_choice(scan_raw.get("mode", "warn"), ("off", "warn", "block"), "warn")),
            tool_guard=ToolGuardPolicy(
                enabled=bool(tg_raw.get("enabled", True)),
                mode=_choice(tg_raw.get("mode", "warn"), ("block", "warn", "require_approval"), "warn"),
            ),
        )

    @classmethod
    def merge(cls, base: SecurityPolicy, override: dict[str, Any] | None) -> SecurityPolicy:
        if not override:
            return base
        base_dict = base.to_dict()
        for key in ("hitl", "filesystem", "pii", "skill_scan", "tool_guard"):
            section = override.get(key)
            if isinstance(section, dict):
                _current = base_dict.get(key)
                current: dict[str, Any] = _current if isinstance(_current, dict) else {}
                base_dict[key] = {**current, **section}
        return cls.from_dict(base_dict)

    def resolve_interrupt_on(self) -> dict[str, Any] | None:
        if not self.hitl.enabled:
            return None
        tool_names = list(DEFAULT_HITL_TOOLS) if self.hitl.tools == "default" else list(self.hitl.tools)
        if not tool_names:
            return None
        entry: dict[str, Any] = {"allowed_decisions": list(self.hitl.allowed_decisions)}
        result: dict[str, Any] = {name: dict(entry) for name in tool_names}

        # Filesystem deny is a hard fail (FilesystemGuard / deepagents permissions).
        # HITL runs in after_model *before* tools execute, so without a `when`
        # predicate write_file/edit_file on a denied path would still pop an
        # approval card — then fail after approve. Skip interrupt when deny wins.
        permissions = self.resolve_permissions()
        if permissions:
            from octop_harness.middleware.filesystem_guard import (
                filesystem_guard_block_reason,
            )

            fs_hitl_tools = {
                name
                for name in result
                if name
                in {
                    "ls",
                    "read_file",
                    "glob",
                    "grep",
                    "write_file",
                    "edit_file",
                }
            }
            for tool_name in fs_hitl_tools:

                def _when(
                    req: Any,
                    *,
                    _tool: str = tool_name,
                    _perms: list[Any] = permissions,
                ) -> bool:
                    tool_call = getattr(req, "tool_call", None) or {}
                    raw_args = tool_call.get("args") if isinstance(tool_call, dict) else {}
                    params: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
                    return not bool(filesystem_guard_block_reason(_perms, tool_name=_tool, params=params))

                result[tool_name] = {**entry, "when": _when}

        return result

    def resolve_permissions(self) -> list[Any] | None:
        if not self.filesystem.enabled or not self.filesystem.rules:
            return None

        out: list[FilesystemPermission] = []
        for rule in self.filesystem.rules:
            if not rule.paths:
                continue
            out.append(
                FilesystemPermission(
                    operations=list(rule.operations),
                    paths=list(rule.paths),
                    mode=rule.mode,
                )
            )
        return out or None

    def apply_to_config(self, cfg: HarnessAgentConfig) -> HarnessAgentConfig:
        """Return a copy of *cfg* with security fields populated from this policy.

        For execution-capable backends, ``permissions`` remain set so
        :class:`~octop_harness.middleware.filesystem_guard.FilesystemGuardMiddleware`
        can enforce them. deepagents only receives permissions when the backend
        does not support shell execution (see ``HarnessAgent`` graph build).
        """
        permissions = self.resolve_permissions()
        return replace(
            cfg,
            interrupt_on=self.resolve_interrupt_on(),
            permissions=permissions,
            pii_enabled=self.pii.enabled,
            pii_strategy=self.pii.strategy,
            pii_surfaces=self.pii.surfaces,
            tool_guard_enabled=self.tool_guard.enabled,
            tool_guard_mode=self.tool_guard.mode,
        )


__all__ = [
    "DEFAULT_HITL_TOOLS",
    "DEFAULT_SENSITIVE_PATHS",
    "FilesystemPolicy",
    "FilesystemRule",
    "HitlPolicy",
    "PiiPolicy",
    "SecurityPolicy",
    "SkillScanPolicy",
    "ToolGuardMode",
    "ToolGuardPolicy",
]
