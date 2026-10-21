"""Cache-Control for dashboard SPA shell vs hashed Vite assets."""

from __future__ import annotations

from pathlib import Path

import pytest
import starlette.responses
from fastapi.responses import FileResponse

from octop.api.app import (
    _dashboard_response,
    dashboard_cache_control,
    is_dashboard_asset_path,
)
from octop.api.content_types import ui_content_type


def test_shell_files_are_revalidated() -> None:
    assert dashboard_cache_control("") == "no-cache"
    assert dashboard_cache_control("index.html") == "no-cache"
    assert dashboard_cache_control("sw.js") == "no-cache"
    assert dashboard_cache_control("manifest.json") == "no-cache"


def test_hashed_assets_are_immutable() -> None:
    assert (
        dashboard_cache_control("assets/index.abc123.js") == "public, max-age=31536000, immutable"
    )
    assert (
        dashboard_cache_control("assets/vendor-utils.Xyz.css")
        == "public, max-age=31536000, immutable"
    )


def test_other_static_files_leave_cache_unset() -> None:
    assert dashboard_cache_control("logo_vertical_dark.svg") is None
    assert dashboard_cache_control("offline.html") is None


def test_only_hashed_assets_skip_the_spa_fallback() -> None:
    assert is_dashboard_asset_path("assets/index.abc123.js") is True
    assert is_dashboard_asset_path("chat") is False
    assert is_dashboard_asset_path("") is False


def test_web_asset_types_are_pinned_not_guessed() -> None:
    # The host may map .js to text/plain (#1940); these must not move.
    assert ui_content_type("index.abc123.js") == "text/javascript; charset=utf-8"
    assert ui_content_type("worker.mjs") == "text/javascript; charset=utf-8"
    assert ui_content_type("index.html") == "text/html; charset=utf-8"
    assert ui_content_type("style.css") == "text/css; charset=utf-8"
    assert ui_content_type("ICON.PNG") == "image/png"


def test_unknown_suffix_is_left_to_the_caller() -> None:
    assert ui_content_type("archive.zip") is None
    assert ui_content_type("README") is None


def test_dashboard_js_ignores_a_hostile_host_mime_map(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A host that maps .js to text/plain must not change what the dashboard serves.

    ``mimetypes`` reads the Windows registry, so a rewritten .js association
    used to make every ES module fail to load (#1940).
    """
    asset = tmp_path / "index.abc123.js"
    asset.write_text("export const x = 1;\n", encoding="utf-8")

    def _hostile_guess_type(url: str, strict: bool = True):  # noqa: ANN202
        return ("text/plain", None)

    # ``FileResponse`` resolves the type through this symbol at construction.
    monkeypatch.setattr(starlette.responses, "guess_type", _hostile_guess_type)

    # Control: without a pinned type the host decides and breaks the module.
    assert FileResponse(asset).headers["content-type"].startswith("text/plain")

    response = _dashboard_response(asset, "assets/index.abc123.js")
    assert response.headers["content-type"].startswith("text/javascript")
