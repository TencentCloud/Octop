"""Workspace subagent loading for deepagents."""

from octop_harness.subagents.catalog import DEFAULT_SUBAGENT_EMOJI, list_subagent_summaries
from octop_harness.subagents.loader import (
    load_subagents_from_workspace,
    merge_subagents,
    parse_agent_markdown,
)

__all__ = [
    "DEFAULT_SUBAGENT_EMOJI",
    "list_subagent_summaries",
    "load_subagents_from_workspace",
    "merge_subagents",
    "parse_agent_markdown",
]
