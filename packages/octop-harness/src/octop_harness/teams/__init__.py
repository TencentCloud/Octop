"""Teams: optional inbox-driven agent-to-agent collaboration."""

from __future__ import annotations

from octop_harness.teams.inbox import (
    HarnessAgentInboxManager,
    InboxMessage,
    InboxStatus,
    PeerResult,
)
from octop_harness.teams.processor import (
    ReplyEvent,
    ReplyStatus,
    TeamProcessor,
    default_compose_followup,
)
from octop_harness.teams.team_manager import TeamManager
from octop_harness.teams.tools import AskAgentInput, build_team_tools
from octop_harness.teams.util import (
    PeerCall,
    PeerSession,
    build_one_shot_request,
    derive_peer_thread_id,
)

__all__ = [
    "AskAgentInput",
    "HarnessAgentInboxManager",
    "InboxMessage",
    "InboxStatus",
    "PeerCall",
    "PeerResult",
    "PeerSession",
    "ReplyEvent",
    "ReplyStatus",
    "TeamManager",
    "TeamProcessor",
    "build_one_shot_request",
    "build_team_tools",
    "default_compose_followup",
    "derive_peer_thread_id",
]
