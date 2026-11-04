"""Multi-field secure forms (masked dialog → env slots / user vault).

The ``request_secure_form`` tool pauses the agent turn on a dedicated
interrupt. The dashboard renders a modal from the server-registered schema;
values travel once through the secure-form submit flow into env slots or the
encrypted ``vault_items`` table and never appear in chat history, model
context, or logs. Storage lives in ``envelope.py`` / ``vault_service.py``;
this package's tool/middleware/validation slice owns registration.
"""

from octop.infra.agents.secure_form.tool import (
    REQUEST_SECURE_FORM_TOOL_NAME,
    SECURE_FORM_HEADLESS_FALLBACK,
    SECURE_FORM_INTERRUPT_ON,
    RequestSecureFormArgs,
    build_request_secure_form_tool,
)
from octop.infra.agents.secure_form.validation import (
    extract_secure_form_request,
    normalize_secure_form_origin,
    secure_form_refusal_decisions,
    validate_secure_form_action_requests,
    validate_secure_form_args,
)

__all__ = [
    "REQUEST_SECURE_FORM_TOOL_NAME",
    "SECURE_FORM_HEADLESS_FALLBACK",
    "SECURE_FORM_INTERRUPT_ON",
    "RequestSecureFormArgs",
    "build_request_secure_form_tool",
    "extract_secure_form_request",
    "normalize_secure_form_origin",
    "secure_form_refusal_decisions",
    "validate_secure_form_action_requests",
    "validate_secure_form_args",
]
