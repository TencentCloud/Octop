"""Mini-games plugin must keep a requested range that starts at zero."""

from __future__ import annotations

import importlib.util
import json
from typing import Any

from octop.infra.agents.plugins.bundled import default_bundled_plugins_root


def _load_mini_games() -> Any:
    path = default_bundled_plugins_root() / "mini-games" / "main.py"
    spec = importlib.util.spec_from_file_location("bundled_mini_games", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def _call(**kwargs: Any) -> tuple[dict[str, Any], str]:
    mod = _load_mini_games()
    payload = json.loads(await mod.guess_number(**kwargs))
    return payload["data"], payload["text"]


async def test_zero_low_range_is_kept() -> None:
    data, text = await _call(low=0, high=50)
    assert data["low"] == 0
    assert data["high"] == 50
    assert "0 到 50" in text


async def test_zero_low_single_step_range_is_not_replaced() -> None:
    data, _ = await _call(low=0, high=1)
    assert (data["low"], data["high"]) == (0, 1)


async def test_zero_low_guess_still_compares_against_secret() -> None:
    data, text = await _call(low=0, high=5, guess=0, secret=3)
    assert data["hint"] == "low"
    assert "0 太小了" in text
    assert data["low"] == 0


async def test_positive_range_still_respected() -> None:
    data, _ = await _call(low=10, high=20)
    assert (data["low"], data["high"]) == (10, 20)


async def test_defaults_apply_when_args_omitted() -> None:
    data, _ = await _call()
    assert (data["low"], data["high"]) == (1, 100)


async def test_inverted_range_falls_back_to_default() -> None:
    data, _ = await _call(low=50, high=10)
    assert (data["low"], data["high"]) == (1, 100)
