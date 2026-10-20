"""Tests for octop_harness.cli.ui.theme."""

from octop_harness.cli.ui.theme import Theme, get_theme


def test_get_theme_dark() -> None:
    theme = get_theme("dark")
    assert isinstance(theme, Theme)
    assert theme.name == "dark"
    assert theme.user_prompt_style is not None


def test_get_theme_light() -> None:
    theme = get_theme("light")
    assert theme.name == "light"


def test_get_theme_invalid_falls_back_to_dark() -> None:
    theme = get_theme("invalid")
    assert theme.name == "dark"
