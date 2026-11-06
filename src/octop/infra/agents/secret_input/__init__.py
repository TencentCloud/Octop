"""Chat-collected secrets via paused turns: single-field and multi-field.

``request_secret_input`` (one masked field → encrypted ``agent_secrets`` slot
→ env injection) and ``request_secure_form`` (a 1-8 field masked dialog → env
slots and/or the encrypted ``vault_items`` table). Both tools pause the agent
turn on a dedicated interrupt; values travel exactly once through the
dedicated submit endpoints and never appear in chat history, model context,
or logs.
"""

from octop.infra.agents.secret_input.service import AgentSecretService
from octop.infra.agents.secret_input.tool import (
    REQUEST_SECRET_INPUT_TOOL_NAME,
    REQUEST_SECURE_FORM_TOOL_NAME,
    SECRET_INPUT_HEADLESS_FALLBACK,
    SECRET_INPUT_INTERRUPT_ON,
    SECURE_FORM_HEADLESS_FALLBACK,
    SECURE_FORM_INTERRUPT_ON,
    RequestSecureFormArgs,
    build_request_secret_input_tool,
    build_request_secure_form_tool,
)
from octop.infra.agents.secret_input.validation import (
    AGENT_SECRET_MAX_VALUE_CHARS,
    extract_secure_form_request,
    normalize_secure_form_origin,
    normalize_slot_name,
    secure_form_refusal_decisions,
    validate_secure_form_action_requests,
    validate_secure_form_args,
)

__all__ = [
    "AGENT_SECRET_MAX_VALUE_CHARS",
    "REQUEST_SECRET_INPUT_TOOL_NAME",
    "REQUEST_SECURE_FORM_TOOL_NAME",
    "SECRET_INPUT_HEADLESS_FALLBACK",
    "SECRET_INPUT_INTERRUPT_ON",
    "SECURE_FORM_HEADLESS_FALLBACK",
    "SECURE_FORM_INTERRUPT_ON",
    "RequestSecureFormArgs",
    "AgentSecretService",
    "build_request_secret_input_tool",
    "build_request_secure_form_tool",
    "extract_secure_form_request",
    "normalize_secure_form_origin",
    "normalize_slot_name",
    "secure_form_refusal_decisions",
    "validate_secure_form_action_requests",
    "validate_secure_form_args",
]
