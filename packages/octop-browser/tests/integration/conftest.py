import pytest

from octop_browser.cdp.launcher import find_chrome


def pytest_collection_modifyitems(config, items):
    """Skip all integration tests if Chrome is not installed."""
    if find_chrome() is None:
        skip = pytest.mark.skip(reason="Chrome/Chromium not installed")
        for item in items:
            if "integration" in str(item.fspath):
                item.add_marker(skip)
