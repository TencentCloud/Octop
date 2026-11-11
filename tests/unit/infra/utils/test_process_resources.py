"""Runtime NOFILE guard covers direct and container starts (Octop#2060)."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from octop.infra.utils import process_resources


@pytest.mark.parametrize(
    ("soft", "hard", "expected"),
    [(1024, 1048576, 65535), (1024, 4096, 4096), (1024, -1, 65535)],
)
def test_raise_soft_limit_without_changing_hard_limit(monkeypatch, caplog, soft, hard, expected):
    resource = SimpleNamespace(
        RLIMIT_NOFILE=7,
        RLIM_INFINITY=-1,
        getrlimit=Mock(return_value=(soft, hard)),
        setrlimit=Mock(),
    )
    monkeypatch.setattr(process_resources.sys, "platform", "linux")
    monkeypatch.setitem(process_resources.sys.modules, "resource", resource)
    with caplog.at_level(logging.INFO):
        process_resources.ensure_nofile_limit()
    resource.setrlimit.assert_called_once_with(7, (expected, hard))
    assert f"soft={expected}" in caplog.text


@pytest.mark.parametrize("soft", [65535, 1048576, -1])
def test_existing_high_or_unlimited_soft_limit_is_kept(monkeypatch, soft):
    resource = SimpleNamespace(
        RLIMIT_NOFILE=7,
        RLIM_INFINITY=-1,
        getrlimit=Mock(return_value=(soft, -1)),
        setrlimit=Mock(),
    )
    monkeypatch.setattr(process_resources.sys, "platform", "linux")
    monkeypatch.setitem(process_resources.sys.modules, "resource", resource)
    process_resources.ensure_nofile_limit()
    resource.setrlimit.assert_not_called()


def test_denied_raise_warns_and_keeps_startup_alive(monkeypatch, caplog):
    resource = SimpleNamespace(
        RLIMIT_NOFILE=7,
        RLIM_INFINITY=-1,
        getrlimit=Mock(return_value=(1024, 65535)),
        setrlimit=Mock(side_effect=OSError("denied")),
    )
    monkeypatch.setattr(process_resources.sys, "platform", "linux")
    monkeypatch.setitem(process_resources.sys.modules, "resource", resource)
    process_resources.ensure_nofile_limit()
    assert "denied" in caplog.text
    assert "1024" in caplog.text


def test_windows_does_not_import_resource(monkeypatch):
    monkeypatch.setattr(process_resources.sys, "platform", "win32")
    monkeypatch.setitem(process_resources.sys.modules, "resource", None)
    process_resources.ensure_nofile_limit()
