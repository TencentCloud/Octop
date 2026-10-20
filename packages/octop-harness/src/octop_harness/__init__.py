"""octop-harness: production-grade Harness Agent on top of LangChain Deep Agents."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

from octop_harness._version import __version__
from octop_harness.config import (
    HarnessAgentConfig,
    MediaGenerationConfig,
    MediaProviderConfig,
    ModelConfig,
    ProviderConfig,
)
from octop_harness.request import ChatRequest

if TYPE_CHECKING:
    from octop_harness.agent import HarnessAgent
    from octop_harness.init import InitResult, init_workspace
    from octop_harness.manager import AgentEntry, HarnessAgentManager
    from octop_harness.observability.logging import (
        current_log_file,
        default_log_dir,
        setup_logging,
        teardown_logging,
    )
    from octop_harness.protocols.langgraph import AgentEventType
    from octop_harness.providers import ModelPreset, ProviderPreset

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "AgentEntry": ("octop_harness.manager", "AgentEntry"),
    "HarnessAgentManager": ("octop_harness.manager", "HarnessAgentManager"),
    "ModelPreset": ("octop_harness.providers", "ModelPreset"),
    "ProviderPreset": ("octop_harness.providers", "ProviderPreset"),
    "HarnessAgent": ("octop_harness.agent", "HarnessAgent"),
    "InitResult": ("octop_harness.init", "InitResult"),
    "init_workspace": ("octop_harness.init", "init_workspace"),
    "current_log_file": ("octop_harness.observability.logging", "current_log_file"),
    "default_log_dir": ("octop_harness.observability.logging", "default_log_dir"),
    "setup_logging": ("octop_harness.observability.logging", "setup_logging"),
    "teardown_logging": ("octop_harness.observability.logging", "teardown_logging"),
    "ChatProtocol": ("octop_harness.protocols", "ChatProtocol"),
    "register_protocol": ("octop_harness.protocols", "register_protocol"),
    "resolve_protocol": ("octop_harness.protocols", "resolve_protocol"),
    "AgentEventType": ("octop_harness.protocols.langgraph", "AgentEventType"),
    "SecurityPolicy": ("octop_harness.security.models", "SecurityPolicy"),
}


def __getattr__(name: str) -> object:  # pragma: no cover - thin re-export shim
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = target
    return getattr(import_module(module_name), attr)


__all__ = [
    "AgentEntry",
    "AgentEventType",
    "ChatProtocol",
    "ChatRequest",
    "HarnessAgent",
    "HarnessAgentConfig",
    "HarnessAgentManager",
    "InitResult",
    "MediaGenerationConfig",
    "MediaProviderConfig",
    "ModelConfig",
    "ModelPreset",
    "ProviderConfig",
    "ProviderPreset",
    "SecurityPolicy",
    "__version__",
    "current_log_file",
    "default_log_dir",
    "init_workspace",
    "register_protocol",
    "resolve_protocol",
    "setup_logging",
    "teardown_logging",
]
