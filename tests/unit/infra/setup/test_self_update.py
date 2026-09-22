"""Tests for octop.infra.setup.self_update."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.setup.self_update import (
    UpgradeResult,
    build_upgrade_command,
    is_newer,
    is_prerelease,
    parse_version,
    pick_latest_versions,
    restore_console_scripts,
    run_upgrade,
    stash_console_scripts,
)


def test_pep440_order() -> None:
    assert parse_version("0.9.34a1") < parse_version("0.9.34b1")
    assert parse_version("0.9.34b1") < parse_version("0.9.34rc1")
    assert parse_version("0.9.34rc1") < parse_version("0.9.34")
    assert parse_version("0.9.34-beta.1") == parse_version("0.9.34b1")
    assert parse_version("0.7.2") > parse_version("0.7.1")


def test_is_prerelease() -> None:
    assert is_prerelease("0.9.34b1")
    assert is_prerelease("0.9.34-beta.1")
    assert is_prerelease("0.9.34rc1")
    assert is_prerelease("0.9.34a1")
    assert is_prerelease("0.9.34.dev1")
    assert not is_prerelease("0.9.34")
    assert not is_prerelease("0.7.1")


def test_is_newer() -> None:
    assert is_newer("0.7.2", "0.7.1")
    assert not is_newer("0.7.1", "0.7.2")
    assert not is_newer("0.7.1", "0.7.1")
    assert is_newer("0.9.34", "0.9.34b1")
    assert is_newer("0.9.34b1", "0.9.33")
    assert not is_newer("0.9.34b1", "0.9.34")


def test_pick_latest_versions_splits_stable_and_pre() -> None:
    latest_any, latest_stable = pick_latest_versions(["0.9.33", "0.9.34b1", "0.9.32", "0.9.34a1"])
    assert latest_any == "0.9.34b1"
    assert latest_stable == "0.9.33"


def test_pick_latest_versions_all_prerelease() -> None:
    latest_any, latest_stable = pick_latest_versions(["0.9.34b1", "0.9.34a1"])
    assert latest_any == "0.9.34b1"
    assert latest_stable is None


def test_build_upgrade_command_prerelease_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    python = "/home/user/.octop/venv/bin/python"
    uv_cmd = build_upgrade_command("uv", python, allow_prerelease=True, version="0.9.34b1")
    assert uv_cmd is not None
    assert uv_cmd[uv_cmd.index("--prerelease") + 1] == "allow"
    assert "octop==0.9.34b1" in uv_cmd
    monkeypatch.setattr("octop.infra.setup.self_update.has_pip", lambda _: True)
    pip_cmd = build_upgrade_command("pip", python, allow_prerelease=True, version="0.9.34b1")
    assert pip_cmd is not None
    assert "--pre" in pip_cmd
    assert "octop==0.9.34b1" in pip_cmd


def test_build_upgrade_command_pins_stable_without_pre(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    python = "/home/user/.octop/venv/bin/python"
    uv_cmd = build_upgrade_command("uv", python, version="0.9.33")
    assert uv_cmd is not None
    assert "octop==0.9.33" in uv_cmd
    assert "--prerelease" not in uv_cmd
    monkeypatch.setattr("octop.infra.setup.self_update.has_pip", lambda _: True)
    pip_cmd = build_upgrade_command("pip", python, version="0.9.33")
    assert pip_cmd is not None
    assert "octop==0.9.33" in pip_cmd
    assert "--pre" not in pip_cmd


def _fake_windows_scripts(tmp_path: Path) -> Path:
    script_dir = tmp_path / "Scripts"
    script_dir.mkdir()
    (script_dir / "python.exe").write_text("python")
    (script_dir / "octop.exe").write_text("launcher")
    (script_dir / "octop.exe.octop-old").write_text("leftover")
    (script_dir / "pip.exe").write_text("pip")
    return script_dir


def test_stash_console_scripts_is_noop_off_windows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("octop.infra.setup.self_update._is_windows", lambda: False)
    script_dir = _fake_windows_scripts(tmp_path)
    assert stash_console_scripts(str(script_dir / "python.exe")) == []
    assert (script_dir / "octop.exe").exists()


def test_stash_console_scripts_moves_launcher_and_purges_leftovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("octop.infra.setup.self_update._is_windows", lambda: True)
    script_dir = _fake_windows_scripts(tmp_path)

    moved = stash_console_scripts(str(script_dir / "python.exe"))

    assert moved == [(script_dir / "octop.exe", script_dir / "octop.exe.octop-old")]
    assert not (script_dir / "octop.exe").exists()
    # The leftover from an earlier upgrade is gone, replaced by the new stash.
    assert (script_dir / "octop.exe.octop-old").read_text() == "launcher"
    assert (script_dir / "pip.exe").exists()


def test_restore_console_scripts_puts_launcher_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("octop.infra.setup.self_update._is_windows", lambda: True)
    script_dir = _fake_windows_scripts(tmp_path)
    moved = stash_console_scripts(str(script_dir / "python.exe"))

    restore_console_scripts(moved)

    assert (script_dir / "octop.exe").read_text() == "launcher"
    assert not (script_dir / "octop.exe.octop-old").exists()


@pytest.mark.parametrize("success", [True, False])
def test_run_upgrade_restores_launcher_only_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    success: bool,
) -> None:
    monkeypatch.setattr("octop.infra.setup.self_update._is_windows", lambda: True)
    monkeypatch.delenv("OCTOP_FPK_SITE_PACKAGES", raising=False)
    script_dir = _fake_windows_scripts(tmp_path)
    monkeypatch.setattr(
        "octop.infra.setup.self_update.resolve_venv_python",
        lambda: str(script_dir / "python.exe"),
    )

    def fake_upgrade(**_kwargs: object) -> UpgradeResult:
        # The installer only succeeds because the locked launcher moved aside.
        assert not (script_dir / "octop.exe").exists()
        if success:
            (script_dir / "octop.exe").write_text("new launcher")
            return UpgradeResult(success=True, installed_version="1.0.1")
        return UpgradeResult(success=False, error="upgrade failed on all mirrors")

    monkeypatch.setattr("octop.infra.setup.self_update._run_managed_upgrade", fake_upgrade)

    result = run_upgrade()

    assert result.success is success
    expected = "new launcher" if success else "launcher"
    assert (script_dir / "octop.exe").read_text() == expected
    assert not (script_dir / "octop.exe.octop-old").exists()
