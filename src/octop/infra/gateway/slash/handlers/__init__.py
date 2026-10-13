"""Gateway slash command handler registry."""

from __future__ import annotations

from octop.infra.gateway.slash.catalog import CATALOG
from octop.infra.gateway.slash.dispatcher import SlashDispatcher
from octop.infra.gateway.slash.handlers.composite import COMPOSITE_HANDLERS
from octop.infra.gateway.slash.handlers.hitl import HITL_HANDLERS
from octop.infra.gateway.slash.handlers.memory import cmd_memory
from octop.infra.gateway.slash.handlers.platform import PLATFORM_HANDLERS
from octop.infra.gateway.slash.handlers.session import SESSION_HANDLERS
from octop.infra.gateway.slash.types import GatewayHandler

GATEWAY_HANDLERS: dict[str, GatewayHandler] = {
    "memory": cmd_memory,
    **SESSION_HANDLERS,
    **PLATFORM_HANDLERS,
    **COMPOSITE_HANDLERS,
    **HITL_HANDLERS,
}


def register_all(d: SlashDispatcher) -> None:
    for spec in CATALOG:
        handler = GATEWAY_HANDLERS.get(spec.name)
        if handler is None:
            continue
        d.register(spec, handler)
