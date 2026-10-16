"""weather plugin must label every WMO code Open-Meteo documents.

Open-Meteo returns only numeric weather codes and documents the mapping it can
emit; the plugin's table skipped several of them, so the card showed the raw
number ("天气码 86") and fell back to a thermometer icon.
"""

from __future__ import annotations

import importlib.util

import pytest

from octop.infra.agents.plugins.bundled import default_bundled_plugins_root

# https://open-meteo.com/en/docs -> "WMO Weather interpretation codes (WW)"
OPEN_METEO_CODES = [
    0,
    1,
    2,
    3,
    45,
    48,
    51,
    53,
    55,
    56,
    57,
    61,
    63,
    65,
    66,
    67,
    71,
    73,
    75,
    77,
    80,
    81,
    82,
    85,
    86,
    95,
    96,
    97,
    99,
]


def _load_plugin():
    path = default_bundled_plugins_root() / "weather" / "main.py"
    spec = importlib.util.spec_from_file_location("bundled_weather", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load_plugin()


@pytest.mark.parametrize("code", OPEN_METEO_CODES)
def test_documented_code_is_not_echoed_as_a_raw_number(code: int) -> None:
    assert not mod._wmo_label(code).startswith("天气码"), code


@pytest.mark.parametrize("code", OPEN_METEO_CODES)
def test_documented_code_has_an_explicit_icon(code: int) -> None:
    assert mod._wmo_icon(code) != "🌡️", code
