"""CloudBase skill plugin (kind=skill).

Declares a single skill directory; on agent start Octop syncs
skills/<name>/SKILL.md into the agent workspace.
"""

from __future__ import annotations

from octop_harness.plugins import PluginContext


def setup(ctx: PluginContext) -> None:
    # Path is relative to the plugin root; each subdirectory must contain SKILL.md.
    ctx.skills("skills")
