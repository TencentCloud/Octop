"""Contract tests for ``read_geometry()``.

``GET /api/desktop/geometry`` parses whatever ``read_geometry()`` returns, so the
read side must only hand back values ``parse_geometry()`` accepts. The file-side
guard used to be the weaker ``_GEOMETRY_RE`` (shape only, no size range) and the
``OCTOP_DESKTOP_GEOMETRY`` fallback had no guard at all, so a geometry that the
shipped ``resize.sh`` / ``install.sh --geometry`` happily accept (e.g. ``800x400``)
escaped the read side and surfaced in the router as an unhandled ``ValueError``.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from octop.infra.desktop.setup import (
    _DEFAULT_GEOMETRY,
    desktop_env_file,
    parse_geometry,
    read_geometry,
)

# Pass the file-side shape check ``^(\d{3,5})x(\d{3,5})$`` but not the size range.
OUT_OF_RANGE = ["800x400", "640x400", "1024x200", "100x100", "8000x600", "1920x4321"]

# Fail the shape check outright.
MALFORMED = ["abc", "1920", "1920x1080x1", ""]

USABLE = ["640x480", "1024x768", "1920x1080", "7680x4320"]

# Both line shapes ``read_geometry()`` understands in ``desktop.env``.
ENV_PREFIXES = ("export OCTOP_DESKTOP_GEOMETRY=", "OCTOP_DESKTOP_GEOMETRY=")


@pytest.fixture(autouse=True)
def _geometry_isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Pin ``OCTOP_HOME`` so ``desktop.env`` writes cannot reach a real ``~/.octop``."""
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "octop-home"))
    monkeypatch.delenv("OCTOP_DESKTOP_GEOMETRY", raising=False)
    yield


def _write_env_file(*lines: str) -> Path:
    path = desktop_env_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("prefix", ENV_PREFIXES)
@pytest.mark.parametrize("value", OUT_OF_RANGE)
def test_out_of_range_file_value_is_not_returned(prefix: str, value: str) -> None:
    path = _write_env_file(prefix + value, "export DISPLAY=:99")
    assert path.is_file()
    assert read_geometry() == _DEFAULT_GEOMETRY


@pytest.mark.parametrize("prefix", ENV_PREFIXES)
@pytest.mark.parametrize("value", MALFORMED)
def test_malformed_file_value_is_not_returned(prefix: str, value: str) -> None:
    _write_env_file(prefix + value)
    assert read_geometry() == _DEFAULT_GEOMETRY


@pytest.mark.parametrize("value", OUT_OF_RANGE + MALFORMED)
def test_out_of_range_env_var_is_not_returned(value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    assert not desktop_env_file().exists()
    monkeypatch.setenv("OCTOP_DESKTOP_GEOMETRY", value)
    assert read_geometry() == _DEFAULT_GEOMETRY


@pytest.mark.parametrize("prefix", ENV_PREFIXES)
@pytest.mark.parametrize("value", USABLE)
def test_usable_file_value_passes_through_untouched(prefix: str, value: str) -> None:
    _write_env_file(prefix + value, "export DISPLAY=:99")
    assert read_geometry() == value


def test_usable_env_var_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTOP_DESKTOP_GEOMETRY", "1024x768")
    assert read_geometry() == "1024x768"


def test_default_geometry_is_returned_when_nothing_is_configured() -> None:
    assert read_geometry() == _DEFAULT_GEOMETRY


@pytest.mark.parametrize("value", OUT_OF_RANGE + MALFORMED)
def test_returned_geometry_always_parses(value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTOP_DESKTOP_GEOMETRY", value)
    parse_geometry(read_geometry())


def test_env_file_writes_stay_under_the_pinned_octop_home(tmp_path: Path) -> None:
    """Contract for the fixture above: ``desktop.env`` must never land in ``~/.octop``."""
    path = _write_env_file(ENV_PREFIXES[0] + "1920x1080", "export DISPLAY=:99")
    assert path == tmp_path / "octop-home" / "desktop" / "desktop.env"
    assert read_geometry() == "1920x1080"
