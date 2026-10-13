"""Client-address resolution for rate limiting.

The header is caller-supplied, so trusting it unconditionally would let anyone
reset a throttle by varying it. These cases pin the trust rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from octop.api.common.client_ip import UNKNOWN_CLIENT, resolve_client_ip


@dataclass
class _Client:
    host: str | None = None


@dataclass
class _Request:
    """Minimal ASGI request surface used by the resolver."""

    peer: str | None = None
    forwarded_for: str | None = None
    client: Any = field(init=False)
    headers: dict[str, str] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        self.client = _Client(self.peer) if self.peer is not None else None
        if self.forwarded_for is not None:
            self.headers = {"x-forwarded-for": self.forwarded_for}


def test_direct_peer_is_used_and_the_header_is_ignored():
    """A client talking straight to us cannot name its own address."""
    request = _Request(peer="203.0.113.7", forwarded_for="10.0.0.1")
    assert resolve_client_ip(request) == "203.0.113.7"


def test_loopback_peer_may_forward_the_client_address():
    request = _Request(peer="127.0.0.1", forwarded_for="203.0.113.7")
    assert resolve_client_ip(request) == "203.0.113.7"


def test_forwarded_chain_takes_the_right_most_hop():
    """A trusted proxy appends what it saw; values to its left may be forged."""
    request = _Request(peer="::1", forwarded_for="1.2.3.4, 203.0.113.7")
    assert resolve_client_ip(request) == "203.0.113.7"


def test_a_client_supplied_prefix_cannot_choose_its_own_bucket():
    """The attacker controls the left of the chain, not the appended hop."""
    honest = _Request(peer="127.0.0.1", forwarded_for="203.0.113.7")
    forged = _Request(peer="127.0.0.1", forwarded_for="9.9.9.9, 203.0.113.7")
    assert resolve_client_ip(forged) == resolve_client_ip(honest)


def test_loopback_peer_without_the_header_falls_back_to_the_peer():
    assert resolve_client_ip(_Request(peer="127.0.0.1")) == "127.0.0.1"


def test_missing_peer_collapses_to_a_single_bucket():
    """Better one shared bucket than a fresh one per request."""
    assert resolve_client_ip(_Request()) == UNKNOWN_CLIENT
    assert resolve_client_ip(_Request(peer="")) == UNKNOWN_CLIENT


def test_blank_header_entries_are_ignored():
    request = _Request(peer="127.0.0.1", forwarded_for=" , ")
    assert resolve_client_ip(request) == "127.0.0.1"
