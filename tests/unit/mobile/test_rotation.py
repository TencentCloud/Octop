"""Unit tests for adb device rotation helpers."""

from __future__ import annotations

from unittest.mock import patch

from octop.infra.mobile.adb import (
    get_display_rotation,
    get_user_rotation,
    is_emulator_device,
    set_user_rotation,
    toggle_portrait_landscape,
)


def test_get_user_rotation_parses_value() -> None:
    with patch(
        "octop.infra.mobile.adb.shell",
        return_value=(0, "1"),
    ):
        assert get_user_rotation("emulator-5554", adb="/adb") == 1


def test_get_user_rotation_null_is_portrait() -> None:
    with patch(
        "octop.infra.mobile.adb.shell",
        return_value=(0, "null"),
    ):
        assert get_user_rotation("emulator-5554", adb="/adb") == 0


def test_is_emulator_device_by_serial() -> None:
    assert is_emulator_device("emulator-5554", adb="/adb") is True


def test_get_display_rotation_parses_window_manager() -> None:
    dumpsys = "DisplayRotation\n    mRotation=1 mDeferredRotationPauseCount=0\n  Display"
    with patch("octop.infra.mobile.adb.shell", return_value=(0, dumpsys)):
        assert get_display_rotation("device", adb="/adb") == 1


def test_set_user_rotation_success_when_display_matches() -> None:
    calls: list[str] = []

    def fake_shell(_device: str, command: str, *, adb: str | None = None) -> tuple[int, str]:
        calls.append(command)
        if command.startswith("dumpsys window"):
            return 0, "DisplayRotation\n    mRotation=1\n"
        if command.startswith("settings get"):
            return 0, "1"
        return 0, ""

    with patch("octop.infra.mobile.adb.shell", side_effect=fake_shell):
        result = set_user_rotation("redmi-phone", 1, adb="/adb")

    assert result.ok is True
    assert result.rotation == 1
    assert any("accelerometer_rotation 0" in c for c in calls)
    assert any("user_rotation 1" in c for c in calls)
    assert any("cmd window user-rotation lock 1" in c for c in calls)


def test_set_user_rotation_physical_falls_back_to_settings() -> None:
    def fake_shell(_device: str, command: str, *, adb: str | None = None) -> tuple[int, str]:
        if command.startswith("dumpsys window"):
            return 0, "DisplayRotation\n    mRotation=0\n"
        if command.startswith("settings get"):
            return 0, "1"
        return 0, ""

    with patch("octop.infra.mobile.adb.shell", side_effect=fake_shell):
        result = set_user_rotation("redmi-phone", 1, adb="/adb")

    assert result.ok is True
    assert result.rotation == 1


def test_set_user_rotation_emulator_reports_unsupported() -> None:
    def fake_shell(_device: str, command: str, *, adb: str | None = None) -> tuple[int, str]:
        if command.startswith("dumpsys window"):
            return 0, "DisplayRotation\n    mRotation=0\n"
        if command.startswith("settings get"):
            return 0, "1"
        return 0, ""

    with (
        patch("octop.infra.mobile.adb.shell", side_effect=fake_shell),
        patch("octop.infra.mobile.adb._try_emulator_rotate"),
    ):
        result = set_user_rotation("emulator-5554", 1, adb="/adb")

    assert result.ok is False
    assert result.rotation == 0
    assert result.message == "emulator_rotation_unsupported"


def test_set_user_rotation_verifies_readback() -> None:
    def fake_shell(_device: str, command: str, *, adb: str | None = None) -> tuple[int, str]:
        if command.startswith("dumpsys window"):
            return 0, "DisplayRotation\n    mRotation=0\n"
        if command.startswith("settings get"):
            return 0, "0"
        return 0, ""

    with patch("octop.infra.mobile.adb.shell", side_effect=fake_shell):
        result = set_user_rotation("redmi-phone", 1, adb="/adb")

    assert result.ok is False
    assert result.rotation == 0
    assert result.message == "rotation_not_applied"


def test_toggle_portrait_landscape_from_portrait() -> None:
    with (
        patch("octop.infra.mobile.adb.get_display_rotation", return_value=0),
        patch("octop.infra.mobile.adb.set_user_rotation") as set_rot,
    ):
        from octop.infra.mobile.adb import RotationResult

        set_rot.return_value = RotationResult(True, 1, "")
        result = toggle_portrait_landscape("device", adb="/adb")

    set_rot.assert_called_once_with("device", 1, adb="/adb")
    assert result.ok is True


def test_toggle_portrait_landscape_from_landscape() -> None:
    with (
        patch("octop.infra.mobile.adb.get_display_rotation", return_value=1),
        patch("octop.infra.mobile.adb.set_user_rotation") as set_rot,
    ):
        from octop.infra.mobile.adb import RotationResult

        set_rot.return_value = RotationResult(True, 0, "")
        toggle_portrait_landscape("device", adb="/adb")

    set_rot.assert_called_once_with("device", 0, adb="/adb")
