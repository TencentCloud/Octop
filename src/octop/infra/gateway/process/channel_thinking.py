"""Patch octop-gateway inbound cleaning to honour Octop thinking helpers."""

from __future__ import annotations

from octop.infra.utils.llm_text import prepare_channel_text

_PATCHED = False


def install_channel_thinking_clean() -> None:
    """Replace ``BaseChannel._clean_output`` with Octop's broader strip/format.

    Upstream only strips ``<think>`` and skips proactive ``push_text``. Octop
    upgrades inbound reply cleaning here; ``Gateway.push_text`` cleans pushes.
    """
    global _PATCHED
    if _PATCHED:
        return
    from octop_gateway.channel import BaseChannel

    def _clean_output(self: BaseChannel, text: str) -> str:  # noqa: ANN001
        constraints = self.constraints
        return prepare_channel_text(
            text,
            show_thinking=bool(constraints.show_thinking),
            thinking_template=str(
                getattr(constraints, "thinking_template", None) or "💭 Thinking: {content}"
            ),
        )

    BaseChannel._clean_output = _clean_output  # type: ignore[method-assign]
    _PATCHED = True
