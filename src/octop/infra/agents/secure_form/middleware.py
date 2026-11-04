"""HITL channel for ``request_secure_form``.

A dedicated :class:`HumanInTheLoopMiddleware` instance rather than a
``cfg.interrupt_on`` entry, mirroring :class:`SecretInputMiddleware`: the
harness gates config-derived interrupts behind bootstrap completion, but a
form can be requested on the very first turn. The distinct class name also
keeps deepagents' custom-middleware merge from replacing the harness's own
HITL instance or the secret-input channel.
"""

from __future__ import annotations

from typing import Any, cast

from langchain.agents.middleware import HumanInTheLoopMiddleware, InterruptOnConfig

from octop.infra.agents.secure_form.tool import (
    REQUEST_SECURE_FORM_TOOL_NAME,
    SECURE_FORM_INTERRUPT_ON,
)


class SecureFormMiddleware(HumanInTheLoopMiddleware):
    """``respond``-only interrupt channel for the masked secure-form dialog."""

    def __init__(self) -> None:
        entry: dict[str, Any] = SECURE_FORM_INTERRUPT_ON[REQUEST_SECURE_FORM_TOOL_NAME]
        config: dict[str, bool | InterruptOnConfig] = {
            REQUEST_SECURE_FORM_TOOL_NAME: cast(InterruptOnConfig, entry)
        }
        super().__init__(interrupt_on=config)


__all__ = ["SecureFormMiddleware"]
