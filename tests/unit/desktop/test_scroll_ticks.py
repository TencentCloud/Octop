"""Tests for remote desktop scroll-delta handling.

The dashboard forwards the browser's raw ``deltaX``/``deltaY`` (see
``dashboard/src/hooks/useCanvasRemotePointer.ts``), so ``InputInjector.scroll`` receives
arbitrary floats from a WebSocket message. Each wheel tick on the xdotool path is a separate
``xdotool`` process, so the tick count has to stay bounded and non-finite deltas must not raise.
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock

from octop.infra.desktop.input import InputInjector

# Any sane per-event bound is far below this; asserting a limit rather than one exact
# constant keeps the guard honest if the cap is retuned.
_TICK_LIMIT = 100

# ``scroll`` divides the delta by a pixels-per-notch factor, so these are the tick counts the
# shipped conversion produces for realistic wheel values.
_NOTCH_PX = 40.0


def _force_xdotool(monkeypatch) -> list[list[str]]:
    """Route the injector down the xdotool branch and record every call.

    Fails as soon as the loop passes the bound, so a runaway count is a crisp assertion
    instead of tens of millions of recorded calls.
    """
    # InputInjector picks xdotool via is_linux_virtual_display (capture.sys.platform).
    monkeypatch.setattr("octop.infra.desktop.capture.sys.platform", "linux")
    monkeypatch.setattr("octop.infra.desktop.input.shutil.which", lambda name: "/usr/bin/xdotool")
    calls: list[list[str]] = []
    ticks: list[str] = []

    def fake_run(_display: str | None, args: list[str]) -> bool:
        calls.append(args)
        if args[0] == "click":
            ticks.append(args[-1])
            assert len(ticks) <= _TICK_LIMIT, f"one wheel event spawned {len(ticks)} xdotool clicks"
        return True

    monkeypatch.setattr("octop.infra.desktop.input._run_xdotool", fake_run)
    return calls


def _ticks(calls: list[list[str]]) -> list[list[str]]:
    return [args for args in calls if args[0] == "click"]


def _pynput_injector(monkeypatch) -> tuple[InputInjector, MagicMock]:
    monkeypatch.setattr("octop.infra.desktop.capture.sys.platform", "win32")
    inj = InputInjector(display=None)
    mouse = MagicMock()
    monkeypatch.setattr(inj, "_controllers", lambda: (mouse, MagicMock()))
    monkeypatch.setattr(inj, "_with_display", lambda fn: fn())
    return inj, mouse


def test_virtual_display_small_delta_is_one_tick(monkeypatch) -> None:
    """A nudge below one notch still scrolls a notch, in the direction of the delta."""
    calls = _force_xdotool(monkeypatch)
    inj = InputInjector(display=":99")

    inj.scroll(10, 20, delta_x=0, delta_y=_NOTCH_PX / 2)
    inj.scroll(10, 20, delta_x=0, delta_y=-_NOTCH_PX / 2)
    inj.scroll(10, 20, delta_x=_NOTCH_PX / 2, delta_y=0)
    inj.scroll(10, 20, delta_x=-_NOTCH_PX / 2, delta_y=0)

    assert _ticks(calls) == [["click", "5"], ["click", "4"], ["click", "6"], ["click", "7"]]


def test_virtual_display_scales_ticks_with_the_delta(monkeypatch) -> None:
    calls = _force_xdotool(monkeypatch)
    inj = InputInjector(display=":99")

    inj.scroll(10, 20, delta_x=0, delta_y=300)

    assert len(_ticks(calls)) == int(300 / _NOTCH_PX)
    assert all(args == ["click", "5"] for args in _ticks(calls))


def test_virtual_display_huge_delta_stays_bounded(monkeypatch) -> None:
    """One wheel message must not spawn a runaway number of xdotool processes."""
    calls = _force_xdotool(monkeypatch)
    inj = InputInjector(display=":99")

    inj.scroll(10, 20, delta_x=0, delta_y=1e9)

    # Still a real scroll, not a silent drop.
    assert _ticks(calls)


def test_pynput_huge_delta_stays_bounded(monkeypatch) -> None:
    inj, mouse = _pynput_injector(monkeypatch)

    inj.scroll(10, 20, delta_x=0, delta_y=1e9)

    assert mouse.scroll.call_count == 1
    (amount_x, amount_y) = mouse.scroll.call_args_list[0][0]
    assert amount_x == 0
    assert abs(amount_y) <= _TICK_LIMIT
    assert amount_y < 0


def test_pynput_matches_the_xdotool_tick_count(monkeypatch) -> None:
    """The pynput branch must keep the counts the xdotool branch produces."""
    inj, mouse = _pynput_injector(monkeypatch)

    inj.scroll(10, 20, delta_x=0, delta_y=30)
    inj.scroll(10, 20, delta_x=0, delta_y=-30)
    inj.scroll(10, 20, delta_x=0, delta_y=100)

    assert [call[0][1] for call in mouse.scroll.call_args_list] == [-1, 1, -int(100 / _NOTCH_PX)]


def test_non_finite_delta_is_dropped_without_raising(monkeypatch) -> None:
    """``json.loads`` accepts ``Infinity``, so a remote message can carry a non-finite delta."""
    calls = _force_xdotool(monkeypatch)
    inj = InputInjector(display=":99")

    for delta in (math.inf, -math.inf, math.nan):
        inj.scroll(10, 20, delta_x=delta, delta_y=delta)

    assert _ticks(calls) == []


def test_non_finite_delta_does_not_raise_on_the_pynput_branch(monkeypatch) -> None:
    inj, mouse = _pynput_injector(monkeypatch)

    for delta in (math.inf, -math.inf, math.nan):
        inj.scroll(10, 20, delta_x=0, delta_y=delta)

    mouse.scroll.assert_not_called()
