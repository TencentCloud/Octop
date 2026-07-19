"""tests/unit/i18n/test_desktop.py"""

from __future__ import annotations

from octop.i18n import all_keys_for_locale, tr


def test_desktop_keys_parity() -> None:
    en_keys = {k for k in all_keys_for_locale("en") if k.startswith("desktop.")}
    zh_keys = {k for k in all_keys_for_locale("zh") if k.startswith("desktop.")}
    assert en_keys == zh_keys
    assert "desktop.install_log_system" in en_keys
    assert "desktop.install_log_build_deps" in en_keys


def test_desktop_error_interpolation() -> None:
    text = tr("desktop.error_command_failed", "en", exit_code=1)
    assert "1" in text
