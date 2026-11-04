"""Optional connector-owned behavior layered on the existing MCP transports.

Only bundled implementations are imported; credentials cannot select Python code.
This dispatch table does not own sessions or introduce a transport/lifecycle API.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from importlib import import_module
from typing import Any, cast

Credentials = dict[str, Any]


@dataclass(frozen=True)
class ConnectorExtension:
    normalize_credentials: Callable[[Credentials], Credentials]
    prepare_credentials: Callable[[Credentials], Awaitable[Credentials]]
    connection_spec: Callable[[Credentials], dict[str, Any]]
    probe: Callable[[Credentials], Awaitable[dict[str, Any]]]
    create_stdio_runtime: Callable[[Any, Any], Any]


# Keep implementation selection in one place, rather than branching in callers.
_MODULES = {"open-design": "octop.infra.connectors.open_design"}


def get_connector_extension(kind: str) -> ConnectorExtension | None:
    module = _MODULES.get(kind)
    if module is None:
        return None
    return cast(ConnectorExtension, import_module(module).connector_extension())
