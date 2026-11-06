"""HITL channel for ``request_secret_input``.

A dedicated :class:`HumanInTheLoopMiddleware` instance rather than a
``cfg.interrupt_on`` entry: the harness gates config-derived interrupts behind
bootstrap completion (onboarding must be able to write files unattended), but a
secret request can happen on the very first turn. The distinct class name also
keeps deepagents' custom-middleware merge from replacing the harness's own HITL
instance, which carries the ``ask_user_question`` and security-tool gates.
"""

from __future__ import annotations

from typing import Any, cast

from langchain.agents.middleware import HumanInTheLoopMiddleware, InterruptOnConfig

from octop.infra.agents.secret_input.tool import (
    REQUEST_SECRET_INPUT_TOOL_NAME,
    SECRET_INPUT_INTERRUPT_ON,
)


class SecretInputMiddleware(HumanInTheLoopMiddleware):
    """``respond``-only interrupt channel for the masked secret card."""

    def __init__(self) -> None:
        entry: dict[str, Any] = SECRET_INPUT_INTERRUPT_ON[REQUEST_SECRET_INPUT_TOOL_NAME]
        config: dict[str, bool | InterruptOnConfig] = {
            REQUEST_SECRET_INPUT_TOOL_NAME: cast(InterruptOnConfig, entry)
        }
        super().__init__(interrupt_on=config)


__all__ = ["SecretInputMiddleware"]
