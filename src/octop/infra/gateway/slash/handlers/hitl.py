"""HITL slash command stubs (IM approval is handled in GlobalProcessor)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from harness_agent.slash import SlashCommand, SlashSink

from octop.i18n.domains.slash import tr
from octop.infra.gateway.slash.ctx import SlashCtx, lang_of
from octop.infra.gateway.slash.types import GatewayHandler

if TYPE_CHECKING:
    from octop.infra.gateway.slash.dispatcher import SlashDispatcher


async def _dashboard_hint(
    d: SlashDispatcher, cmd: SlashCommand, ctx: SlashCtx, sink: SlashSink
) -> None:
    del d, cmd
    await sink.text(tr("hitl.dashboard_hint", lang_of(ctx)))


HITL_HANDLERS: dict[str, GatewayHandler] = {
    "approve": _dashboard_hint,
    "reject": _dashboard_hint,
    "pending": _dashboard_hint,
    "answer": _dashboard_hint,
}
