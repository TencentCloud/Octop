r"""``GET /api/desktop/geometry`` must report a geometry, never 500.

The shipped ``resize.sh`` / ``install.sh --geometry`` write any ``\d{3,5}x\d{3,5}``
value into ``${OCTOP_HOME}/desktop/desktop.env`` and then start Xvnc with it, so a
size outside the range ``parse_geometry()`` enforces is a state the product itself
supports. The route parses ``read_geometry()`` with no error mapping, so before the
read-side guard was tightened it raised a bare ``ValueError`` and the global
handler turned that into ``500 INTERNAL_ERROR`` plus a server traceback.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from octop.infra.desktop.setup import _DEFAULT_GEOMETRY, desktop_env_file, parse_geometry


@pytest.fixture
def geometry_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv("OCTOP_DESKTOP_GEOMETRY", raising=False)
    monkeypatch.delenv("OCTOP_HOME", raising=False)
    yield


def _write_env_file(line: str) -> Path:
    path = desktop_env_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{line}\nexport DISPLAY=:99\n", encoding="utf-8")
    return path


async def test_out_of_range_env_file_falls_back_to_default(env: Any, geometry_env: None) -> None:
    client, _srv, auth = env
    _write_env_file("export OCTOP_DESKTOP_GEOMETRY=800x400")

    r = await client.get("/api/desktop/geometry", headers=auth)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"geometry": _DEFAULT_GEOMETRY, "width": 1920, "height": 1080}
    parse_geometry(body["geometry"])


async def test_usable_env_file_is_reported_verbatim(env: Any, geometry_env: None) -> None:
    client, _srv, auth = env
    _write_env_file("export OCTOP_DESKTOP_GEOMETRY=1024x768")

    r = await client.get("/api/desktop/geometry", headers=auth)

    assert r.status_code == 200, r.text
    assert r.json() == {"geometry": "1024x768", "width": 1024, "height": 768}
