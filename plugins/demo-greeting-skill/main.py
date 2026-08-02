"""Demo Greeting Skill — sample skill plugin (kind=skill).

Skill plugins do not register callable tools. They declare a directory with
ctx.skills(...); on agent start Octop syncs each skills/<name>/SKILL.md into
the agent workspace under skills/.
"""

from __future__ import annotations

from harness_agent.plugins import PluginContext


def setup(ctx: PluginContext) -> None:
    # Path is relative to the plugin root; each subdirectory should contain SKILL.md.
    ctx.skills("skills")
