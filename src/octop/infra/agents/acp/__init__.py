"""Host-side ACP wiring for managed experts.

Protocol conversion and session attach live in octop-harness. This package
decides which MCP servers a managed turn adds, and keeps the chat cards aligned
with native file edits.
"""

from octop.infra.agents.acp.file_edits import install_acp_file_edits
from octop.infra.agents.acp.permissions import install_acp_permission_queue
from octop.infra.agents.acp.tool_names import install_acp_tool_titles
from octop.infra.agents.acp.turn import attach_managed_turn

__all__ = [
    "attach_managed_turn",
    "install_acp_file_edits",
    "install_acp_permission_queue",
    "install_acp_tool_titles",
]
