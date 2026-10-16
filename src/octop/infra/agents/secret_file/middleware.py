"""Credential input is a collaboration channel, independent of tool approval."""

from typing import Any

from langchain.agents.middleware import HumanInTheLoopMiddleware

from octop.infra.agents.secret_file.paths import REQUEST_SECRET_FILE_TOOL


class SecretFileInputMiddleware(HumanInTheLoopMiddleware[Any, Any, Any]):
    """Keep a distinct name so DeepAgents preserves its approval middleware."""

    def __init__(self) -> None:
        super().__init__(
            interrupt_on={
                REQUEST_SECRET_FILE_TOOL: {
                    "allowed_decisions": ["respond"],
                    "description": "The agent is asking you to provide a credential file.",
                },
            },
        )
