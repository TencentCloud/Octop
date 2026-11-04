"""Hot-sync DB provider configs into a shared ``HarnessAgentManager`` factory."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from octop_harness.config import ProviderConfig

if TYPE_CHECKING:
    from octop_harness import HarnessAgentManager

logger = logging.getLogger(__name__)


def sync_providers_to_harness(
    harness_manager: HarnessAgentManager,
    providers: list[ProviderConfig],
    *,
    shared_factory: Any | None,
) -> None:
    """Apply *providers* to the harness manager's shared model factory."""
    if shared_factory is None:
        if not providers:
            return
        for provider in providers:
            try:
                harness_manager.add_provider(provider)
            except Exception:
                logger.exception("add_provider %s failed", provider.id)
        return

    new_ids = {provider.id for provider in providers}
    existing_ids = set(getattr(shared_factory, "_providers", {}).keys())
    for provider_id in existing_ids - new_ids:
        try:
            harness_manager.remove_provider(provider_id)
        except Exception:
            logger.exception("remove_provider %s failed", provider_id)
    for provider in providers:
        try:
            harness_manager.add_provider(provider)
        except Exception:
            logger.exception("add_provider %s failed", provider.id)


__all__ = ["sync_providers_to_harness"]
