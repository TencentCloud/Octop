"""Demo UI Card — backend tool that returns an ``octop_ui`` envelope.

The matching frontend renderer lives in ``ui/dist/`` and is loaded by the
Dashboard into the chat tool-result registry.
"""

from __future__ import annotations

import json

from harness_agent.plugins import PluginContext


async def demo_ui_card(title: str = "Hello from plugin UI", count: int = 1) -> str:
    """Return a structured card payload for the Dashboard plugin renderer."""
    payload = {
        "octop_ui": {"renderer": "demo_card", "version": 1},
        "data": {
            "title": title,
            "count": int(count),
            "note": "Click Refresh on the card to patch this result (L2).",
        },
        "text": f"{title} (count={count})",
    }
    return json.dumps(payload, ensure_ascii=False)


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "demo_ui_card",
        demo_ui_card,
        description="Demo tool that renders a custom card in the chat UI",
    )
