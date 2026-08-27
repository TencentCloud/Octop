"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Modules whose tests boot OctopServer, real harness, browser tooling, or bwrap.
# Tagged ``slow`` so ``make test-fast`` can skip them during local iteration.
_SLOW_TEST_MODULES = frozenset(
    {
        "tests/unit/browser/test_browser_setup.py",
        "tests/unit/infra/utils/test_bwrap.py",
        "tests/unit/agents/test_skills_hub_raw.py",
        "tests/unit/agents/test_skillhub_market.py",
        "tests/unit/gateway/test_attachment_hints.py",
        "tests/unit/agents/test_agent_manager.py",
        "tests/unit/agents/test_agent_registry.py",
        "tests/unit/api/test_jwt_auth_middleware.py",
        "tests/unit/api/test_openapi_meta.py",
        "tests/unit/api/test_exception_handlers.py",
    },
)


def _module_path(nodeid: str) -> str:
    return nodeid.split("::", 1)[0]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        module = _module_path(item.nodeid)
        if module in _SLOW_TEST_MODULES or module.startswith("tests/integration/"):
            item.add_marker(pytest.mark.slow)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return _REPO_ROOT


@pytest.fixture(autouse=True)
def _isolated_user_home(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Per-test HOME outside the test's ``tmp_path``.

    Keeping HOME off ``tmp_path`` avoids polluting directory listings and
    colliding with tests that create ``tmp_path / \"home\"`` themselves.
    Required for xdist so workers never share ``~/.octop`` / CLI state.
    """
    home = tmp_path_factory.mktemp("user-home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


@pytest.fixture
def tmp_octop_home(_isolated_user_home: Path) -> Iterator[Path]:
    """Redirect ``~/.octop`` under the autouse isolated HOME."""
    octop = _isolated_user_home / ".octop"
    octop.mkdir(exist_ok=True)
    yield octop
