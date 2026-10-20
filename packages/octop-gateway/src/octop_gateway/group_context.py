"""Shared group-conversation policy and recent-message buffering.

Channels normalize platform events into :class:`InboundMessage` metadata.  This
module then applies the same activation and context rules regardless of the IM
provider.  It deliberately does not own long-term agent/thread memory: the
buffer only contains group chatter that was visible to the bot but did not
start an agent turn.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from octop_gateway.models import ContentPart, GroupContext, GroupContextMessage, InboundMessage, TextContent


class GroupVisibility(StrEnum):
    """Group messages that the platform is expected to expose to the bot."""

    AUTO = "auto"
    ALL = "all"
    MENTION_RECENT = "mention_recent"
    MENTION_ONLY = "mention_only"


class GroupActivation(StrEnum):
    """When a visible group message starts an agent turn."""

    MENTION = "mention"
    ALWAYS = "always"


class GroupHistoryMode(StrEnum):
    """Whether passive group chatter is attached to the next agent turn."""

    RECENT = "recent"
    NONE = "none"


@dataclass(frozen=True)
class GroupContextPolicy:
    """Effective policy for one group conversation."""

    enabled: bool = False
    visibility: GroupVisibility = GroupVisibility.AUTO
    activation: GroupActivation = GroupActivation.MENTION
    history: GroupHistoryMode = GroupHistoryMode.RECENT
    history_limit: int = 10
    history_ttl_seconds: float = 300.0
    clear_after_reply: bool = True


@dataclass
class GroupContextConfig:
    """Serializable default policy with optional per-group overrides.

    ``visibility`` describes the permission granted by the platform/group
    owner, while ``activation`` describes the bot's own reply behaviour.  They
    are separate on purpose: receiving every message does not imply replying
    to every message.
    """

    enabled: bool = False
    visibility: str = GroupVisibility.AUTO
    activation: str = GroupActivation.MENTION
    history: str = GroupHistoryMode.RECENT
    history_limit: int = 10
    history_ttl_seconds: float = 300.0
    clear_after_reply: bool = True
    groups: dict[str, dict[str, object]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> GroupContextConfig:
        raw_groups = data.get("groups")
        groups: dict[str, dict[str, object]] = {}
        if isinstance(raw_groups, dict):
            for conversation_id, override in raw_groups.items():
                if isinstance(conversation_id, str) and isinstance(override, dict):
                    groups[conversation_id] = {str(key): value for key, value in override.items()}
        return cls(
            enabled=bool(data.get("enabled", False)),
            visibility=str(data.get("visibility", GroupVisibility.AUTO)),
            activation=str(data.get("activation", GroupActivation.MENTION)),
            history=str(data.get("history", GroupHistoryMode.RECENT)),
            history_limit=int(str(data.get("history_limit", 10))),
            history_ttl_seconds=float(str(data.get("history_ttl_seconds", 300.0))),
            clear_after_reply=bool(data.get("clear_after_reply", True)),
            groups=groups,
        )

    def resolve(self, conversation_id: str) -> GroupContextPolicy:
        policy = self._policy_from_mapping(
            {
                "enabled": self.enabled,
                "visibility": self.visibility,
                "activation": self.activation,
                "history": self.history,
                "history_limit": self.history_limit,
                "history_ttl_seconds": self.history_ttl_seconds,
                "clear_after_reply": self.clear_after_reply,
            }
        )
        wildcard = self.groups.get("*")
        if isinstance(wildcard, dict):
            policy = self._overlay(policy, wildcard)
        specific = self.groups.get(conversation_id)
        if isinstance(specific, dict):
            policy = self._overlay(policy, specific)
        return policy

    @staticmethod
    def _policy_from_mapping(data: Mapping[str, object]) -> GroupContextPolicy:
        return GroupContextPolicy(
            enabled=bool(data.get("enabled", False)),
            visibility=_enum_value(GroupVisibility, data.get("visibility"), GroupVisibility.AUTO),
            activation=_enum_value(GroupActivation, data.get("activation"), GroupActivation.MENTION),
            history=_enum_value(GroupHistoryMode, data.get("history"), GroupHistoryMode.RECENT),
            history_limit=max(0, int(str(data.get("history_limit", 10)))),
            history_ttl_seconds=max(0.0, float(str(data.get("history_ttl_seconds", 300.0)))),
            clear_after_reply=bool(data.get("clear_after_reply", True)),
        )

    @classmethod
    def _overlay(cls, base: GroupContextPolicy, values: Mapping[str, object]) -> GroupContextPolicy:
        raw = {
            "enabled": values.get("enabled", base.enabled),
            "visibility": values.get("visibility", base.visibility),
            "activation": values.get("activation", base.activation),
            "history": values.get("history", base.history),
            "history_limit": values.get("history_limit", base.history_limit),
            "history_ttl_seconds": values.get("history_ttl_seconds", base.history_ttl_seconds),
            "clear_after_reply": values.get("clear_after_reply", base.clear_after_reply),
        }
        return cls._policy_from_mapping(raw)


def _enum_value[StrEnumT: StrEnum](enum_type: type[StrEnumT], value: object, default: StrEnumT) -> StrEnumT:
    try:
        return enum_type(str(value))
    except ValueError:
        return default


class GroupContextManager:
    """Apply group activation rules and keep bounded passive-message history."""

    def __init__(self, config: GroupContextConfig | None = None) -> None:
        self._config = config or GroupContextConfig()
        self._buffers: dict[str, deque[GroupContextMessage]] = {}

    def handles(self, message: InboundMessage) -> bool:
        conversation_id = self._conversation_id(message)
        return bool(conversation_id and self._config.resolve(conversation_id).enabled)

    def should_persist_media(self, message: InboundMessage) -> bool:
        """Whether media must survive long enough to reach the agent.

        Current-turn media is always retained. Passive group media is retained
        only when the effective policy will buffer recent context; mention-only
        and history-disabled groups intentionally avoid the download.
        """
        context_has_media = bool(
            message.group_context
            and any(
                not isinstance(part, TextContent) for item in message.group_context.messages for part in item.content
            )
        )
        if not message.has_media and not context_has_media:
            return False
        conversation_id = self._conversation_id(message)
        if not conversation_id:
            return True
        policy = self._config.resolve(conversation_id)
        if not policy.enabled:
            return True
        if self._should_process(message, policy):
            return True
        return (
            policy.visibility is not GroupVisibility.MENTION_ONLY
            and policy.history is GroupHistoryMode.RECENT
            and policy.history_limit > 0
        )

    def prepare(self, message: InboundMessage) -> InboundMessage | None:
        """Record passive chatter or enrich a message that should reach the agent."""
        conversation_id = self._conversation_id(message)
        if not conversation_id:
            return message
        policy = self._config.resolve(conversation_id)
        if not policy.enabled:
            message.group_context = None
            return message

        self._expire(conversation_id, policy, now=message.timestamp)
        activation, capability_degraded = self._effective_activation(policy)
        should_process = activation is GroupActivation.ALWAYS or bool(message.metadata.get("bot_mentioned"))
        if not should_process:
            if policy.visibility is not GroupVisibility.MENTION_ONLY and policy.history is GroupHistoryMode.RECENT:
                self._append(conversation_id, message, policy)
            return None

        platform_messages = message.group_context.messages if message.group_context else []
        buffered = self._merge_messages(
            platform_messages,
            list(self._buffers.get(conversation_id, ())),
        )
        if policy.history is GroupHistoryMode.NONE or policy.visibility is GroupVisibility.MENTION_ONLY:
            buffered = []

        message.group_context = GroupContext(
            conversation_id=conversation_id,
            visibility=policy.visibility,
            activation=activation,
            messages=buffered[-policy.history_limit :] if policy.history_limit else [],
            capability_degraded=capability_degraded,
        )
        return message

    @staticmethod
    def _merge_messages(
        platform_messages: list[GroupContextMessage],
        buffered_messages: list[GroupContextMessage],
    ) -> list[GroupContextMessage]:
        """Merge platform-supplied recent context with locally observed events."""
        merged: list[GroupContextMessage] = []
        seen: set[str] = set()
        for item in [*platform_messages, *buffered_messages]:
            media = ",".join(str(getattr(part, "url", "") or getattr(part, "local_path", "")) for part in item.content)
            key = item.message_id or f"{item.sender_id}\0{item.text}\0{media}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
        return merged

    @staticmethod
    def _effective_activation(policy: GroupContextPolicy) -> tuple[GroupActivation, bool]:
        """Return safe activation plus whether the requested mode degraded."""
        activation = policy.activation
        if activation is GroupActivation.ALWAYS and policy.visibility is not GroupVisibility.ALL:
            return GroupActivation.MENTION, True
        return activation, False

    @classmethod
    def _should_process(cls, message: InboundMessage, policy: GroupContextPolicy) -> bool:
        activation, _ = cls._effective_activation(policy)
        return activation is GroupActivation.ALWAYS or bool(message.metadata.get("bot_mentioned"))

    def mark_replied(self, message: InboundMessage) -> None:
        """Clear one-shot passive context after a successful agent turn."""
        conversation_id = self._conversation_id(message)
        if not conversation_id:
            return
        policy = self._config.resolve(conversation_id)
        if policy.enabled and policy.clear_after_reply:
            self._buffers.pop(conversation_id, None)

    def clear(self, conversation_id: str) -> None:
        """Purge retained context after a permission/configuration downgrade."""
        self._buffers.pop(conversation_id, None)

    @staticmethod
    def _conversation_id(message: InboundMessage) -> str:
        value = message.metadata.get("conversation_id")
        if isinstance(value, str) and value:
            return value
        if message.channel_subject and message.channel_subject.chat_type == "group":
            return message.channel_subject.subject_id
        return ""

    def _append(
        self,
        conversation_id: str,
        message: InboundMessage,
        policy: GroupContextPolicy,
    ) -> None:
        if policy.history_limit <= 0:
            return
        text = message.text.strip()
        content: list[ContentPart] = [
            part.model_copy(deep=True) for part in message.content if not isinstance(part, TextContent)
        ]
        if not text and not content:
            return
        entry = GroupContextMessage(
            message_id=str(message.metadata.get("msg_id") or message.metadata.get("message_id") or ""),
            sender_id=str(message.metadata.get("sender_id") or "unknown"),
            sender_name=str(message.metadata.get("sender_name") or ""),
            text=text,
            content=content,
            timestamp=message.timestamp,
        )
        buffer = self._buffers.setdefault(conversation_id, deque())
        if entry.message_id and any(item.message_id == entry.message_id for item in buffer):
            return
        buffer.append(entry)
        while len(buffer) > policy.history_limit:
            buffer.popleft()

    def _expire(self, conversation_id: str, policy: GroupContextPolicy, *, now: float) -> None:
        if policy.history_ttl_seconds <= 0:
            self._buffers.pop(conversation_id, None)
            return
        buffer = self._buffers.get(conversation_id)
        if not buffer:
            return
        cutoff = (now or time.time()) - policy.history_ttl_seconds
        while buffer and buffer[0].timestamp < cutoff:
            buffer.popleft()
        if not buffer:
            self._buffers.pop(conversation_id, None)
