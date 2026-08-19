"""tests/unit/mobile/test_mobile_setup.py"""

from __future__ import annotations

from unittest.mock import patch

from octop.config import CapabilitiesConfig, MobileCapabilities, OctopConfig
from octop.infra.mobile.setup import mobile_status


def _cfg(**mobile: object) -> OctopConfig:
    return OctopConfig(
        capabilities=CapabilitiesConfig(
            mobile=MobileCapabilities(**mobile)  # type: ignore[arg-type]
        )
    )


def test_mobile_status_disabled() -> None:
    status = mobile_status(_cfg(enabled=False, backend="none"))
    assert status.mobile_supported is False
    assert status.setup_state == "unsupported"


def test_mobile_status_physical_ready() -> None:
    with (
        patch("octop.infra.mobile.setup.find_adb", return_value="/adb"),
        patch("octop.infra.mobile.setup.list_devices", return_value=["emulator-5554"]),
    ):
        status = mobile_status(_cfg(enabled=True, backend="physical"))
    assert status.setup_state == "ready"
    assert status.selected_device == "emulator-5554"


def test_mobile_status_physical_needs_device() -> None:
    with (
        patch("octop.infra.mobile.setup.find_adb", return_value="/adb"),
        patch("octop.infra.mobile.setup.list_devices", return_value=[]),
    ):
        status = mobile_status(_cfg(enabled=True, backend="physical"))
    assert status.setup_state == "needs_device"
