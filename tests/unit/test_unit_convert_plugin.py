"""Unit-convert plugin must never emit a non-standard JSON envelope."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from typing import Any

import pytest

from octop.infra.agents.plugins.bundled import default_bundled_plugins_root


def _load_unit_convert():
    path = default_bundled_plugins_root() / "unit-convert" / "main.py"
    spec = importlib.util.spec_from_file_location("bundled_unit_convert", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _strict_envelope(output: str) -> dict[str, Any]:
    """Parse the tool envelope the way the dashboard does (``JSON.parse``)."""

    def _reject(token: str) -> Any:
        raise ValueError(f"non-standard JSON token: {token}")

    return json.loads(output, parse_constant=_reject)


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan"), "1e999"])
def test_non_finite_value_returns_error_card(value: Any) -> None:
    mod = _load_unit_convert()
    output = asyncio.run(mod.convert_unit(value, "km", "mi"))
    envelope = _strict_envelope(output)

    assert envelope["data"]["error"] == "value must be finite"
    assert envelope["text"]


def test_overflowing_result_returns_error_card() -> None:
    mod = _load_unit_convert()
    output = asyncio.run(mod.convert_unit(1e308, "km", "cm"))
    envelope = _strict_envelope(output)

    assert envelope["data"]["error"] == "result out of range"
    assert envelope["text"]


def test_finite_conversion_is_unchanged() -> None:
    mod = _load_unit_convert()
    envelope = _strict_envelope(asyncio.run(mod.convert_unit(1.5, "km", "m")))

    assert envelope["data"]["result"] == 1500.0
    assert envelope["data"]["category"] == "length"
