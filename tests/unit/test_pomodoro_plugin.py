"""Pomodoro countdown must hand the card a timestamp Date.parse accepts."""

from __future__ import annotations

import importlib.util
import json
import re
from datetime import datetime, timedelta
from typing import Any

import pytest

from octop.infra.agents.plugins.bundled import default_bundled_plugins_root


def _load_pomodoro() -> Any:
    path = default_bundled_plugins_root() / "pomodoro" / "main.py"
    spec = importlib.util.spec_from_file_location("bundled_pomodoro", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _data(payload: str) -> dict[str, Any]:
    return json.loads(payload)["data"]


# ECMA-262 §21.4.1.5 "Date Time String Format" — the only shape the renderer's
# `Date.parse(d.target_iso)` is required to understand.
JS_DATE_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3})?(Z|[+-]\d{2}:\d{2})?$")

# Accepted by `datetime.fromisoformat` but not by that grammar.
PY_ONLY_TARGETS = ("20261231", "2026-12-31T18:00:00+08:00:00", "2026-12-31T18:00:00.123456")

COMMON_TARGETS = (
    "2026-12-31",
    "2026-12-31T18:00",
    "2026-12-31 18:00:00",
    "2026-12-31T18:00:00Z",
    "2026-12-31T18:00:00.500Z",
    "2026-12-31T18:00:00+08:00",
    "2026-12-31T18:00:00+0800",
    *PY_ONLY_TARGETS,
)


@pytest.mark.parametrize("target", COMMON_TARGETS)
async def test_countdown_target_is_readable_by_the_card(target: str) -> None:
    mod = _load_pomodoro()
    data = _data(await mod.start_countdown("跨年", target))
    assert "error" not in data
    assert JS_DATE_TIME.match(data["target_iso"]), data["target_iso"]


@pytest.mark.parametrize("target", COMMON_TARGETS)
async def test_countdown_target_keeps_the_validated_moment(target: str) -> None:
    mod = _load_pomodoro()
    data = _data(await mod.start_countdown("跨年", target))
    expected = datetime.fromisoformat(target.replace("Z", "+00:00"))
    # The browser grammar allows three fraction digits, so normalization truncates
    # to milliseconds; anything finer is not a moment the card can represent.
    assert abs(datetime.fromisoformat(data["target_iso"]) - expected) <= timedelta(milliseconds=1)


async def test_countdown_rejects_non_datetime() -> None:
    mod = _load_pomodoro()
    data = _data(await mod.start_countdown("跨年", "next new year"))
    assert data["error"] == "invalid datetime"


async def test_countdown_requires_a_target() -> None:
    mod = _load_pomodoro()
    data = _data(await mod.start_countdown("跨年", "   "))
    assert data["error"] == "target required"
