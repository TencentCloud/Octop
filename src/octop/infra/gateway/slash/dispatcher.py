"""SlashDispatcher: gateway handlers + harness runtime delegation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from harness_agent.slash import (
    RuntimeSlashDispatcher,
    SlashCommand,
    SlashSink,
    build_runtime_dispatcher,
)

from octop.infra.errors import OctopError
from octop.infra.gateway.slash.catalog import SlashCommandSpec, list_specs, spec_for
from octop.infra.gateway.slash.ctx import SlashCtx
from octop.infra.gateway.slash.runtime_bridge import build_runtime_ctx
from octop.infra.gateway.slash.types import GatewayHandler

if TYPE_CHECKING:
    pass


class SlashDispatcher:
    def __init__(self, runtime: RuntimeSlashDispatcher | None = None) -> None:
        self._handlers: dict[str, GatewayHandler] = {}
        self._runtime = runtime or build_runtime_dispatcher()

    def register(self, spec: SlashCommandSpec, handler: GatewayHandler) -> None:
        for n in (spec.name, *spec.aliases):
            self._handlers[n] = handler

    async def handle(self, cmd: SlashCommand, ctx: SlashCtx, sink: SlashSink) -> bool:
        handler = self._handlers.get(cmd.name)
        if handler is None:
            if self._runtime.has(cmd.name):
                runtime_ctx = await build_runtime_ctx(cmd, ctx)
                await self._runtime.handle(cmd, runtime_ctx, sink)
                return True
            return False
        try:
            await handler(self, cmd, ctx, sink)
        except OctopError as exc:
            await sink.text(f"error: {exc.message}")
        await sink.complete()
        return True

    def known(self) -> list[tuple[str, str]]:
        from octop.infra.gateway.slash.catalog import CATALOG  # noqa: PLC0415

        out: list[tuple[str, str]] = []
        for spec in CATALOG:
            if self._handlers.get(spec.name) is None and not self._runtime.has(spec.name):
                continue
            out.append((spec.name, spec.description_for("en")))
        return sorted(out)

    def list_command_specs(self, *, origin: str = "all") -> list[SlashCommandSpec]:
        return list_specs(origin=origin)

    def spec_for(self, name: str) -> SlashCommandSpec | None:
        return spec_for(name)

    def get_thread_model_override(self, ctx: SlashCtx, thread_id: str) -> str | None:
        if ctx.agent_manager is None:
            return None
        return ctx.agent_manager.get_thread_model(ctx.agent_id, thread_id)

    def set_thread_model_override(self, ctx: SlashCtx, thread_id: str, model: str) -> None:
        if ctx.agent_manager is not None:
            ctx.agent_manager.set_thread_model(ctx.agent_id, thread_id, model)

    def clear_thread_model_override(self, ctx: SlashCtx, thread_id: str) -> None:
        if ctx.agent_manager is not None:
            ctx.agent_manager.clear_thread_model(ctx.agent_id, thread_id)


def build_default_dispatcher() -> SlashDispatcher:
    from octop.infra.gateway.slash.handlers import register_all  # noqa: PLC0415

    d = SlashDispatcher()
    register_all(d)
    return d
