"""Tests for the startup NOFILE soft-limit floor (#2060)."""

from __future__ import annotations

import logging
import types

import pytest

from octop import launch


def _fake_resource(soft: int, hard: int, *, deny_setrlimit: bool = False):
    mod = types.SimpleNamespace()
    mod.RLIMIT_NOFILE = 7
    mod.RLIM_INFINITY = -1
    mod.calls: list[tuple[int, int]] = []
    mod.getrlimit = lambda _which: (soft, hard)

    def setrlimit(_which: int, limits: tuple[int, int]) -> None:
        if deny_setrlimit:
            raise OSError("operation not permitted")
        mod.calls.append(limits)

    mod.setrlimit = setrlimit
    return mod


def test_raises_soft_limit_to_hard_cap() -> None:
    mod = _fake_resource(soft=1024, hard=1048576)

    assert launch._apply_nofile_floor(mod) == (1048576, 1048576)
    assert mod.calls == [(1048576, 1048576)]


def test_noop_when_soft_already_at_hard_cap() -> None:
    mod = _fake_resource(soft=1048576, hard=1048576)

    assert launch._apply_nofile_floor(mod) is None
    assert mod.calls == []


def test_infinite_hard_cap_gets_finite_floor() -> None:
    mod = _fake_resource(soft=1024, hard=-1)  # -1 == RLIM_INFINITY in the stub

    assert launch._apply_nofile_floor(mod) == (65535, -1)
    assert mod.calls == [(65535, -1)]


def test_denied_setrlimit_is_swallowed(caplog: pytest.LogCaptureFixture) -> None:
    mod = _fake_resource(soft=1024, hard=1048576, deny_setrlimit=True)

    with caplog.at_level(logging.WARNING):
        launch._raise_nofile_soft_limit(resource_module=mod)

    assert any("NOFILE" in record.message for record in caplog.records)
