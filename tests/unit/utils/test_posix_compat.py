"""Tests for POSIX compat helpers used by the web terminal."""

from __future__ import annotations

import os

import pytest

from octop.infra.utils import posix_compat

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX only")


@posix_only
def test_setsid_tolerates_none_return(monkeypatch: pytest.MonkeyPatch) -> None:
    """macOS ``os.setsid()`` returns None; wrapping that in ``int()`` must not raise.

    A raising ``preexec_fn`` aborts the PTY shell spawn and the web terminal
    immediately shows “process exited”.
    """
    monkeypatch.setattr(os, "setsid", lambda: None)
    assert posix_compat.setsid() == 0


@posix_only
def test_setsid_preserves_int_return(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "setsid", lambda: 42)
    assert posix_compat.setsid() == 42
