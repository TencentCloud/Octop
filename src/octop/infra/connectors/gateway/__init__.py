"""In-process MCP gateway for wkbuddy-hosted connector adapters."""

from octop.infra.connectors.gateway.langchain import build_gateway_langchain_tools
from octop.infra.connectors.gateway.protocol import handle_mcp_request
from octop.infra.connectors.gateway.registry import mcp_tools_for_kind

__all__ = [
    "build_gateway_langchain_tools",
    "handle_mcp_request",
    "mcp_tools_for_kind",
]
