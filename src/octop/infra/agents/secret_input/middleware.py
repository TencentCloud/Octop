"""HITL channels for the secret-input / secure-form tools.

A dedicated :class:`HumanInTheLoopMiddleware` instance per tool rather than a
``cfg.interrupt_on`` entry: the harness gates config-derived interrupts behind
bootstrap completion (onboarding must be able to write files unattended), but a
secret or form request can happen on the very first turn. The distinct class
names also keep deepagents' custom-middleware merge from replacing the
harness's own HITL instance (which carries the ``ask_user_question`` and
security-tool gates) or each other.
"""

from __future__ import annotations

from typing import Any, cast

from langchain.agents.middleware import HumanInTheLoopMiddleware, InterruptOnConfig

from octop.infra.agents.secret_input.tool import (
    REQUEST_SECRET_INPUT_TOOL_NAME,
    REQUEST_SECURE_FORM_TOOL_NAME,
    SECRET_INPUT_INTERRUPT_ON,
    SECURE_FORM_INTERRUPT_ON,
)


class _RespondOnlyHitlMiddleware(HumanInTheLoopMiddleware):
    """Shared base: one ``respond``-only interrupt entry for one tool."""

    def __init__(self, tool_name: str, interrupt_entry: dict[str, Any]) -> None:
        config: dict[str, bool | InterruptOnConfig] = {
            tool_name: cast(InterruptOnConfig, interrupt_entry)
        }
        super().__init__(interrupt_on=config)


class SecretInputMiddleware(_RespondOnlyHitlMiddleware):
    """``respond``-only interrupt channel for the masked secret card."""

    def __init__(self) -> None:
        super().__init__(
            REQUEST_SECRET_INPUT_TOOL_NAME,
            SECRET_INPUT_INTERRUPT_ON[REQUEST_SECRET_INPUT_TOOL_NAME],
        )


class SecureFormMiddleware(_RespondOnlyHitlMiddleware):
    """``respond``-only interrupt channel for the masked secure-form dialog."""

    def __init__(self) -> None:
        super().__init__(
            REQUEST_SECURE_FORM_TOOL_NAME,
            SECURE_FORM_INTERRUPT_ON[REQUEST_SECURE_FORM_TOOL_NAME],
        )


__all__ = ["SecretInputMiddleware", "SecureFormMiddleware"]
