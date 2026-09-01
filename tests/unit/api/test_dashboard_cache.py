"""Cache-Control for dashboard SPA shell vs hashed Vite assets."""

from __future__ import annotations

from octop.api.app import dashboard_cache_control, is_dashboard_asset_path


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
    assert dashboard_cache_control("logo.svg") is None
    assert dashboard_cache_control("offline.html") is None


def test_only_hashed_assets_skip_the_spa_fallback() -> None:
    assert is_dashboard_asset_path("assets/index.abc123.js") is True
    assert is_dashboard_asset_path("chat") is False
    assert is_dashboard_asset_path("") is False
