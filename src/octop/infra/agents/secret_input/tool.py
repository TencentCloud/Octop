"""The ``request_secret_input`` and ``request_secure_form`` agent tools.

Both tool bodies only run in headless contexts (cron, unattended subagents):
interactive paths interrupt before execution via the dedicated middleware so
the values are collected through the submit flows instead of ever becoming
tool arguments.
"""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

REQUEST_SECRET_INPUT_TOOL_NAME = "request_secret_input"
REQUEST_SECURE_FORM_TOOL_NAME = "request_secure_form"

_SECRET_INPUT_DESCRIPTION = (
    "Ask the user to provide a secret (API key, token, password) through a "
    "masked input card. The value is stored encrypted under the given slot "
    "name and injected as an environment variable of the same name for the "
    "commands you execute. You will never see the value itself — do not ask "
    "the user to paste secrets into the chat, and never print or echo the "
    "environment variable's content. Use this tool when a credential is "
    "required to complete the task and the slot is not set yet."
)

_SECURE_FORM_DESCRIPTION = (
    "Ask the user to fill a short secure form (1-8 typed fields) through a "
    "masked dialog. Prefer this over request_secret_input whenever MORE THAN "
    "ONE value is needed — e.g. host + port + username + password, or a card. "
    "You will never see the values themselves. routing.kind 'env' maps each "
    "field to an environment-variable slot injected into your command "
    "executions; 'vault' persists the fields as an encrypted vault item "
    "(login / card / contact). card_cvv and otp fields are never persisted to "
    "the vault. Do not ask the user to paste these values into the chat."
)

SECURE_FORM_FIELD_TYPES = ("text", "password", "otp", "card_number", "card_exp", "card_cvv")
SECURE_FORM_VAULT_ITEM_TYPES = ("login", "card", "contact")

# Model-facing fallbacks for headless runs (cron / unattended): the interrupt
# never reaches a human, so the tool body answers instead of blocking.
SECRET_INPUT_HEADLESS_FALLBACK = (
    "No interactive secret input is available in this context. Continue without "
    "the credential, or ask the user to configure it from the dashboard."
)
SECURE_FORM_HEADLESS_FALLBACK = (
    "No interactive form input is available in this context. Continue without "
    "the requested values, or ask the user to configure them from the dashboard."
)

# Registered on the dedicated middleware instances: ``respond`` only,
# mirroring ``ask_user_question`` — the human answers *instead of* the tool
# body running.
SECRET_INPUT_INTERRUPT_ON: dict[str, dict[str, Any]] = {
    REQUEST_SECRET_INPUT_TOOL_NAME: {
        "allowed_decisions": ["respond"],
        "description": "The agent is asking the user to provide a secret.",
    },
}
SECURE_FORM_INTERRUPT_ON: dict[str, dict[str, Any]] = {
    REQUEST_SECURE_FORM_TOOL_NAME: {
        "allowed_decisions": ["respond"],
        "description": "The agent is asking the user to fill a secure form.",
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


class SecureFormVaultMetaArgs(BaseModel):
    item_type: Literal["login", "card", "contact"] = Field(
        ...,
        description="Vault item type created by this form.",
    )
    title: str = Field(
        ...,
        max_length=120,
        description="Vault item title (unique per item type for this user).",
    )
    origin: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "Optional site origin the credentials belong to, as "
            "scheme://host[:port] with an http(s) scheme (agent-declared, "
            "not verified)."
        ),
    )


class SecureFormRoutingArgs(BaseModel):
    kind: Literal["env", "vault"] = Field(
        ...,
        description="'env' maps fields to environment slots; 'vault' stores them as one item.",
    )
    slots: dict[str, str] | None = Field(
        default=None,
        description=(
            "routing.kind='env': maps every field id to its environment "
            "variable name (letters/digits/underscore, not reserved)."
        ),
    )
    vault_meta: SecureFormVaultMetaArgs | None = Field(
        default=None,
        description=(
            "routing.kind='vault': required item metadata. Optional for 'env' "
            "to offer a save-to-vault checkbox."
        ),
    )


class SecureFormFieldArgs(BaseModel):
    id: str = Field(
        ...,
        max_length=32,
        pattern=r"^[a-z0-9_]+$",
        description="Stable field identifier: lowercase letters, digits, underscores.",
    )
    label: str = Field(..., max_length=60, description="User-facing field label.")
    type: Literal["text", "password", "otp", "card_number", "card_exp", "card_cvv"] = Field(
        ...,
        description="Input type; drives masking and submit-time shape checks.",
    )
    required: bool = Field(default=True, description="Whether the user must fill the field.")
    max_length: int | None = Field(
        default=None,
        ge=1,
        le=256,
        description="Optional maximum value length (<= 256).",
    )


class RequestSecureFormArgs(BaseModel):
    fields: list[SecureFormFieldArgs] = Field(
        ...,
        min_length=1,
        max_length=8,
        description="1-8 typed fields to collect.",
    )
    prompt: str = Field(
        ...,
        max_length=500,
        description="Short user-facing explanation of what the form is used for.",
    )
    title: str | None = Field(
        default=None,
        max_length=60,
        description="Optional dialog title shown above the form.",
    )
    routing: SecureFormRoutingArgs = Field(
        ...,
        description="Where the collected values go (env slots or a vault item).",
    )


async def _request_secret_input_headless(slot: str, prompt: str, title: str | None = None) -> str:
    del slot, prompt, title
    return SECRET_INPUT_HEADLESS_FALLBACK


async def _request_secure_form_headless(
    fields: list[dict[str, Any]],
    prompt: str,
    routing: dict[str, Any],
    title: str | None = None,
) -> str:
    del fields, prompt, routing, title
    return SECURE_FORM_HEADLESS_FALLBACK


def build_request_secret_input_tool() -> StructuredTool:
    return StructuredTool.from_function(
        coroutine=_request_secret_input_headless,
        name=REQUEST_SECRET_INPUT_TOOL_NAME,
        description=_SECRET_INPUT_DESCRIPTION,
        args_schema=RequestSecretInputArgs,
    )


def build_request_secure_form_tool() -> StructuredTool:
    return StructuredTool.from_function(
        coroutine=_request_secure_form_headless,
        name=REQUEST_SECURE_FORM_TOOL_NAME,
        description=_SECURE_FORM_DESCRIPTION,
        args_schema=RequestSecureFormArgs,
    )


__all__ = [
    "REQUEST_SECRET_INPUT_TOOL_NAME",
    "REQUEST_SECURE_FORM_TOOL_NAME",
    "SECURE_FORM_FIELD_TYPES",
    "SECURE_FORM_HEADLESS_FALLBACK",
    "SECURE_FORM_INTERRUPT_ON",
    "SECURE_FORM_VAULT_ITEM_TYPES",
    "SECRET_INPUT_HEADLESS_FALLBACK",
    "SECRET_INPUT_INTERRUPT_ON",
    "RequestSecureFormArgs",
    "RequestSecretInputArgs",
    "build_request_secure_form_tool",
    "build_request_secret_input_tool",
]
