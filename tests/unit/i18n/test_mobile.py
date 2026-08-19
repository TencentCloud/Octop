"""tests/unit/i18n/test_mobile.py"""

from __future__ import annotations

from octop.i18n.loader import all_keys_for_locale


def test_mobile_keys_parity() -> None:
    en_keys = {k for k in all_keys_for_locale("en") if k.startswith("mobile.")}
    zh_keys = {k for k in all_keys_for_locale("zh") if k.startswith("mobile.")}
    assert en_keys == zh_keys
    assert "mobile.no_device" in en_keys
