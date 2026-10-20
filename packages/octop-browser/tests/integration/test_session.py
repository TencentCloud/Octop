"""Integration tests: real Chrome headless + CDP."""

from pathlib import Path

import pytest

from octop_browser.profile import ProfileManager
from octop_browser.session import BrowserSession


@pytest.fixture()
async def sess(tmp_path: Path):
    pm = ProfileManager(base_dir=tmp_path / "profiles")
    try:
        s = await BrowserSession.create(
            profile="test", headless=True, profile_manager=pm
        )
    except RuntimeError as exc:
        if "Chrome" in str(exc) or "Chromium" in str(exc):
            pytest.skip(f"Chrome/Chromium unavailable for integration: {exc}")
        raise
    yield s
    await s.close()


async def test_navigate_returns_success(sess: BrowserSession):
    result = await sess.navigate("data:text/html,<h1>Hello</h1>")
    assert result.success is True
    assert "Navigated" in result.content


async def test_dom_tree_minimal(sess: BrowserSession):
    await sess.navigate("data:text/html,<h1>Test</h1><button>Click me</button>")
    result = await sess.dom_tree(level="minimal")
    assert result.success is True
    assert "Interactive elements" in result.content


async def test_dom_tree_interactive_has_button(sess: BrowserSession):
    await sess.navigate("data:text/html,<button>Submit</button>")
    result = await sess.dom_tree(level="interactive")
    assert result.success is True
    assert "button" in result.content.lower()
    assert "[ref=" in result.content
