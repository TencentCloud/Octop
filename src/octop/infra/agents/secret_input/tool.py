"""The ``request_secret_input`` agent tool.

The tool body only runs in headless contexts (cron, unattended subagents): the
dashboard path interrupts before execution via ``SECRET_INPUT_INTERRUPT_ON`` so
the value is collected through the dedicated submit endpoint instead of ever
becoming a tool argument.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

REQUEST_SECRET_INPUT_TOOL_NAME = "request_secret_input"

_DESCRIPTION = (
    "Ask the user to provide a secret (API key, token, password) through a "
    "masked input card. The value is stored encrypted under the given slot "
    "name and injected as an environment variable of the same name for the "
    "commands you execute. You will never see the value itself — do not ask "
    "the user to paste secrets into the chat, and never print or echo the "
    "environment variable's content. Use this tool when a credential is "
    "required to complete the task and the slot is not set yet."
)

# Model-facing fallback for headless runs (cron / unattended): the interrupt
# never reaches a human, so the tool body answers instead of blocking.
SECRET_INPUT_HEADLESS_FALLBACK = (
    "No interactive secret input is available in this context. Continue without "
    "the credential, or ask the user to configure it from the dashboard."
)

# Registered into harness ``interrupt_on``: ``respond`` only, mirroring
# ``ask_user_question`` — the human answers *instead of* running the tool body.
SECRET_INPUT_INTERRUPT_ON: dict[str, dict[str, Any]] = {
    REQUEST_SECRET_INPUT_TOOL_NAME: {
        "allowed_decisions": ["respond"],
        "description": "The agent is asking the user to provide a secret.",
    },
}


class RequestSecretInputArgs(BaseModel):
    slot: str = Field(
        ...,
        max_length=64,
        description=(
            "Environment variable name to store the secret under, e.g. "
            "STEAM_WEB_API_KEY. Letters, digits and underscores; must not "
            "start with a digit or use the OCTOP_ prefix."
        ),
    )
    prompt: str = Field(
        ...,
        max_length=500,
        description="Short user-facing explanation of what the secret is used for.",
    )
    title: str | None = Field(
        default=None,
        max_length=60,
        description="Optional card title shown above the masked input.",
    )


async def _request_secret_input_headless(slot: str, prompt: str, title: str | None = None) -> str:
    del slot, prompt, title
    return SECRET_INPUT_HEADLESS_FALLBACK


def build_request_secret_input_tool() -> StructuredTool:
    return StructuredTool.from_function(
        coroutine=_request_secret_input_headless,
        name=REQUEST_SECRET_INPUT_TOOL_NAME,
        description=_DESCRIPTION,
        args_schema=RequestSecretInputArgs,
    )


__all__ = [
    "REQUEST_SECRET_INPUT_TOOL_NAME",
    "SECRET_INPUT_HEADLESS_FALLBACK",
    "SECRET_INPUT_INTERRUPT_ON",
    "RequestSecretInputArgs",
    "build_request_secret_input_tool",
]
