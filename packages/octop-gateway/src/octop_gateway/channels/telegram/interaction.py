"""Bounded, expiring, identity-bound native callback capabilities."""

from __future__ import annotations

import secrets
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass
class Callback:
    """A one-shot host action tied to one Telegram conversation and user."""

    user: str
    chat: str
    topic: int | None
    expires: float
    action: Callable[[], Awaitable[None]]


class Interactions:
    """Keep opaque callback data free of privileges or user-controlled actions."""

    def __init__(self) -> None:
        self.pending: OrderedDict[str, Callback] = OrderedDict()

    def register(
        self, user: str, chat: str, topic: int | None, action: Callable[[], Awaitable[None]], *, ttl: float = 300
    ) -> str:
        """Register a short host action; long work must be queued by the host."""
        token = secrets.token_urlsafe(18)
        self.pending[token] = Callback(user, chat, topic, time.monotonic() + ttl, action)
        while len(self.pending) > 1000:
            self.pending.popitem(last=False)
        return token

    async def invoke(self, token: str, user: str, chat: str, topic: int | None) -> bool:
        """Validate scope before consuming; other users cannot invalidate a button."""
        item = self.pending.get(token)
        if item is None:
            return False
        if item.expires < time.monotonic():
            self.pending.pop(token, None)
            return False
        if (item.user, item.chat, item.topic) != (user, chat, topic):
            return False
        self.pending.pop(token)
        await item.action()
        return True
