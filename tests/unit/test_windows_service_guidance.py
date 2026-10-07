"""Windows has no system service backend, so nothing may advertise one.

`octop service` is systemd/launchd only (`detect_platform_mode`), yet the Windows
installers used to end with `octop service start` and the user guide claimed a
Windows service — following either one always fails with
"system services are only supported on Linux and macOS".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.setup import service as service_module

REPO = Path(__file__).resolve().parents[2]
WINDOWS_INSTALLERS = ("scripts/install.ps1", "scripts/install.bat")


@pytest.mark.parametrize("rel", WINDOWS_INSTALLERS)
def test_windows_installers_advertise_only_supported_commands(rel: str) -> None:
    text = (REPO / rel).read_text(encoding="utf-8")
    assert "octop service" not in text, f"{rel} recommends a command Windows cannot run"
    assert "octop run" in text


def test_windows_has_no_service_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module.platform, "system", lambda: "Windows")
    assert service_module.detect_platform_mode() is None


def test_build_runtime_hint_is_actionable_on_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(service_module.platform, "system", lambda: "Windows")
    with pytest.raises(RuntimeError) as raised:
        service_module.build_runtime(home=tmp_path)
    message = str(raised.value)
    assert "Linux and macOS" in message
    assert "octop run" in message


def test_service_status_detail_is_actionable_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module.platform, "system", lambda: "Windows")
    status = service_module.collect_service_status()
    assert status.mode is None
    assert status.installed is False
    assert "octop run" in status.detail
