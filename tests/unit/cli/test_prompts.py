"""Tests for the questionary wrapper (no real TTY)."""

from __future__ import annotations

import pytest

from octop.cli.support import prompts as _prompts


def test_select_returns_selected_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_prompts, "_ask", lambda kind, **kw: "second")
    out = _prompts.select("Pick one:", choices=["first", "second"])
    assert out == "second"


def test_text_returns_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_prompts, "_ask", lambda kind, **kw: "alice")
    assert _prompts.text("Username:") == "alice"


def test_password_returns_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_prompts, "_ask", lambda kind, **kw: "s3cret")
    assert _prompts.password("Password:") == "s3cret"


def test_confirm_returns_bool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_prompts, "_ask", lambda kind, **kw: True)
    assert _prompts.confirm("Sure?") is True


def test_checkbox_returns_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_prompts, "_ask", lambda kind, **kw: ["a", "c"])
    out = _prompts.checkbox("Pick:", choices=["a", "b", "c"])
    assert out == ["a", "c"]


def test_cancel_via_keyboard_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(kind: str, **kw: object) -> object:
        raise KeyboardInterrupt

    monkeypatch.setattr(_prompts, "_ask", _raise)
    with pytest.raises(SystemExit) as exc:
        _prompts.text("name:")
    # Cancelled prompt → graceful exit 130 (Ctrl-C convention)
    assert exc.value.code == 130


def test_ctrl_c_in_a_real_prompt_cancels(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ctrl-C must cancel, not come back as an empty answer (#2611)."""
    import questionary

    class _Question:
        def ask(self) -> None:
            # questionary's ask() prints "Cancelled by user" and returns None
            return None

        def unsafe_ask(self) -> str:
            raise KeyboardInterrupt

    monkeypatch.setattr(questionary, "text", lambda **kw: _Question())
    with pytest.raises(SystemExit) as exc:
        _prompts.text("Display name (optional):")
    assert exc.value.code == 130
