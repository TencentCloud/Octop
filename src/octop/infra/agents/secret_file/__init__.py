"""Secure secret-file card: model requests a credential file, the user fills it.

The model only ever sees request metadata (path, prompt) and a filled /
cancelled / failed status — never the secret itself. The secret travels
browser → authenticated API → the agent's platform-managed auth directory
(``workspace/.octop/auth`` or legacy ``.octop-auth``).
"""

from octop.infra.agents.secret_file.paths import (
    REQUEST_SECRET_FILE_TOOL,
    normalize_secret_name,
    resolve_auth_fragment,
    secret_fragment,
)
from octop.infra.agents.secret_file.private_write import write_secret_private
from octop.infra.agents.secret_file.service import (
    describe_secret_request,
    is_secret_action_requests,
    maybe_annotate_secret_payload,
    secret_request_args,
    submit_secret_content,
)
from octop.infra.agents.secret_file.tool import build_secret_file_tools

__all__ = [
    "REQUEST_SECRET_FILE_TOOL",
    "build_secret_file_tools",
    "describe_secret_request",
    "is_secret_action_requests",
    "maybe_annotate_secret_payload",
    "normalize_secret_name",
    "resolve_auth_fragment",
    "secret_fragment",
    "secret_request_args",
    "submit_secret_content",
    "write_secret_private",
]
