"""Cache-Control and media types for dashboard SPA shell vs hashed Vite assets."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.api.app import dashboard_cache_control, dashboard_media_type, is_dashboard_asset_path


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


def test_dashboard_media_types_are_fixed() -> None:
    assert dashboard_media_type(Path("assets/index.abc123.js")) == "application/javascript"
    assert dashboard_media_type(Path("assets/vendor-utils.Xyz.css")) == "text/css"
    assert dashboard_media_type(Path("index.html")) == "text/html"
    assert dashboard_media_type(Path("assets/logo.svg")) == "image/svg+xml"
    assert dashboard_media_type(Path("assets/icon.woff2")) == "font/woff2"
    assert dashboard_media_type(Path("assets/unknown.bin")) is None


def test_dashboard_response_bypasses_platform_mimetypes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A per-user registry entry (HKCU\Software\Classes\.js) makes Windows
    # mimetypes resolve .js as text/plain; the dashboard must not depend on it.
    import starlette.responses

    from octop.api.app import _dashboard_response

    monkeypatch.setattr(starlette.responses, "guess_type", lambda name: ("text/plain", None))
    response = _dashboard_response(Path("assets/index.abc123.js"), "assets/index.abc123.js")
    assert response.media_type == "application/javascript"
    assert response.headers["Cache-Control"] == "public, max-age=31536000, immutable"
