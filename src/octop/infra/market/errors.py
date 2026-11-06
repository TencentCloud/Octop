"""Errors raised while reading the remote market catalog."""

from __future__ import annotations

from octop.infra.errors import ErrorCode, OctopError


class PortalMarketError(RuntimeError):
    """Raised when the remote catalog or a package cannot be read."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        network: bool = False,
    ) -> None:
        super().__init__(message)
        self.status = status
        # True when this host could not reach the catalog (DNS, refused, timeout).
        # HTTP responses from the catalog stay False: that is the market, not the network.
        self.network = network


def local_network_error(exc: PortalMarketError) -> OctopError | None:
    """Network error only when this host could not reach the catalog.

    Every other catalog failure returns ``None`` so the caller keeps the
    market-unavailable error.
    """
    if not exc.network:
        return None
    return OctopError(ErrorCode.NETWORK_ERROR, "market request failed: network error")
