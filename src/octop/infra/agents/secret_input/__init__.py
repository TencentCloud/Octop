"""Chat-collected secret slots (masked card → encrypted store → env injection).

The ``request_secret_input`` tool pauses the agent turn on an interrupt. The
dashboard renders a masked input card; the value travels exactly once through
the dedicated submit endpoint into the encrypted ``agent_secrets`` table and is
injected as an environment variable when the agent's commands execute. The
plaintext never appears in chat history, model context, or logs.
"""

from octop.infra.agents.secret_input.service import AgentSecretService
from octop.infra.agents.secret_input.slots import (
    AGENT_SECRET_MAX_VALUE_CHARS,
    normalize_slot_name,
)
from octop.infra.agents.secret_input.tool import (
    REQUEST_SECRET_INPUT_TOOL_NAME,
    SECRET_INPUT_HEADLESS_FALLBACK,
    SECRET_INPUT_INTERRUPT_ON,
    build_request_secret_input_tool,
)

__all__ = [
    "AGENT_SECRET_MAX_VALUE_CHARS",
    "AgentSecretService",
    "REQUEST_SECRET_INPUT_TOOL_NAME",
    "SECRET_INPUT_HEADLESS_FALLBACK",
    "SECRET_INPUT_INTERRUPT_ON",
    "build_request_secret_input_tool",
    "normalize_slot_name",
]
