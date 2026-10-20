"""Turn-aware ``model.profile`` for SummarizationMiddleware thresholds.

deepagents builds ``SummarizationMiddleware`` with the compile-time seed model.
Fraction triggers read ``model.profile["max_input_tokens"]`` on every check —
still the seed — while ``ModelRouterMiddleware`` only swaps ``request.model``
later. Installing a dynamic profile on the seed makes those checks follow the
same turn model-ref rules as the router (explicit override, multimodal, default).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from octop_harness.backends.utils import DEFENSIVE_OP_ERRORS
from octop_harness.middleware.turn_model import resolve_turn_model_ref

logger = logging.getLogger(__name__)


def _configurable_from_runtime() -> dict[str, Any]:
    try:
        from langgraph.config import get_config

        config = get_config()
    except RuntimeError:
        return {}
    configurable = config.get("configurable") or {}
    return dict(configurable) if isinstance(configurable, dict) else {}


class TurnAwareProfile(dict[str, Any]):
    """``dict`` subclass so init-time ``isinstance(profile, dict)`` stays true.

    ``compute_summarization_defaults`` requires a real ``dict`` with
    ``max_input_tokens`` to pick fraction triggers. Runtime ``.get`` /
    ``__getitem__`` re-resolve against the turn model from the factory.
    """

    def __init__(
        self,
        base: Mapping[str, Any] | None,
        *,
        factory: Any,
        pick_default_ref: Callable[[], str],
        pick_multimodal_ref: Callable[[], str | None] | None = None,
        messages_provider: Callable[[], Sequence[Any] | None] | None = None,
    ) -> None:
        super().__init__(dict(base or {}))
        self._factory = factory
        self._pick_default_ref = pick_default_ref
        self._pick_multimodal_ref = pick_multimodal_ref
        self._messages_provider = messages_provider

    def _resolve_ref(self) -> str:
        messages = None
        if self._messages_provider is not None:
            try:
                messages = self._messages_provider()
            except DEFENSIVE_OP_ERRORS:
                messages = None
        return resolve_turn_model_ref(
            pick_default_ref=self._pick_default_ref,
            configurable=_configurable_from_runtime(),
            messages=messages,
            pick_multimodal_ref=self._pick_multimodal_ref,
        )

    def _active(self) -> Mapping[str, Any]:
        ref = self._resolve_ref()
        try:
            model = self._factory.get_chat_model(ref)
        except DEFENSIVE_OP_ERRORS:
            logger.debug("turn-aware profile: factory miss for %r", ref, exc_info=True)
            return self
        result: Mapping[str, Any] = self
        profile = getattr(model, "profile", None)
        if profile is self:
            return result
        if isinstance(profile, Mapping):
            mit = profile.get("max_input_tokens") if hasattr(profile, "get") else None
            if isinstance(mit, int) and mit > 0:
                return profile
        return result

    def __getitem__(self, key: str) -> Any:
        active = self._active()
        if active is self:
            return super().__getitem__(key)
        return active[key]

    def get(self, key: str, default: Any = None) -> Any:
        active = self._active()
        if active is self:
            return super().get(key, default)
        return active.get(key, default)

    def __contains__(self, key: object) -> bool:
        active = self._active()
        if active is self:
            return super().__contains__(key)
        return key in active


def install_turn_aware_profile(
    seed: Any,
    *,
    factory: Any,
    pick_default_ref: Callable[[], str],
    pick_multimodal_ref: Callable[[], str | None] | None = None,
    messages_provider: Callable[[], Sequence[Any] | None] | None = None,
) -> Any:
    """Replace ``seed.profile`` with a :class:`TurnAwareProfile` (in place)."""
    raw = getattr(seed, "profile", None)
    base: dict[str, Any] = dict(raw) if isinstance(raw, Mapping) else {}
    aware = TurnAwareProfile(
        base,
        factory=factory,
        pick_default_ref=pick_default_ref,
        pick_multimodal_ref=pick_multimodal_ref,
        messages_provider=messages_provider,
    )
    try:
        object.__setattr__(seed, "profile", aware)
    except (AttributeError, TypeError):
        seed.profile = aware
    return seed


__all__ = [
    "TurnAwareProfile",
    "install_turn_aware_profile",
]
