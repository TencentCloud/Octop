"""Tests for octop.infra.setup.self_update."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.setup.self_update import (
    UpgradeResult,
    _all_mirrors_failed,
    build_upgrade_command,
    index_label,
    is_newer,
    is_prerelease,
    page_has_package_version,
    parse_version,
    pick_latest_versions,
    probe_index,
    rank_install_indexes,
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


def test_page_has_package_version_matches_wheel_and_sdist() -> None:
    body = '<a href="octop-1.0.1-py3-none-any.whl">octop-1.0.1-py3-none-any.whl</a>'
    assert page_has_package_version(body, "1.0.1")
    assert not page_has_package_version(body, "1.0.10")
    assert page_has_package_version(
        '<a href="octop-1.0.2.tar.gz">octop-1.0.2.tar.gz</a>',
        "1.0.2",
    )
    assert page_has_package_version("any non-empty body", None)
    assert not page_has_package_version("   ", None)


def test_index_label_prefers_hostname() -> None:
    assert index_label("https://pypi.org/simple") == "pypi.org"
    assert (
        index_label("https://mirrors.cloud.tencent.com/pypi/simple") == "mirrors.cloud.tencent.com"
    )


def test_probe_index_classifies_missing_and_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Resp:
        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'<a href="octop-0.9.0-py3-none-any.whl">x</a>'

    monkeypatch.setattr(
        "octop.infra.setup.self_update.urllib.request.urlopen",
        lambda *_a, **_k: _Resp(),
    )
    missing = probe_index("https://mirrors.example/simple", version="1.0.1", timeout=1)
    assert missing.status == "missing_version"
    assert "1.0.1" in missing.detail

    def _boom(*_a: object, **_k: object) -> None:
        raise TimeoutError("timed out")

    monkeypatch.setattr("octop.infra.setup.self_update.urllib.request.urlopen", _boom)
    bad = probe_index("https://down.example/simple", version="1.0.1", timeout=1)
    assert bad.status == "unreachable"
    assert bad.detail.startswith("timeout:")


def test_rank_install_indexes_skips_missing_prefers_fast_hit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.infra.setup import self_update

    def fake_probe(
        index_url: str,
        *,
        version: str | None = None,
        timeout: float = 8,
    ) -> self_update.IndexProbe:
        label = self_update.index_label(index_url)
        if "tencent" in index_url:
            return self_update.IndexProbe(
                index_url, label, 0.05, "missing_version", "missing_version 1.2.3"
            )
        if "aliyun" in index_url:
            return self_update.IndexProbe(index_url, label, 0.02, "has_version")
        if "tuna" in index_url:
            return self_update.IndexProbe(index_url, label, 0.01, "has_version")
        if "ustc" in index_url:
            return self_update.IndexProbe(index_url, label, 0.2, "unreachable", "unreachable: down")
        return self_update.IndexProbe(index_url, label, 0.03, "has_version")

    monkeypatch.setattr(self_update, "probe_index", fake_probe)
    ordered, skips = rank_install_indexes("1.2.3")
    labels = [label for _url, label in ordered]
    assert labels[0] == "pypi.tuna.tsinghua.edu.cn"
    assert labels[1] == "mirrors.aliyun.com"
    assert labels[-1] == "pypi.org"
    assert any("tencent" in err and "missing_version" in err for err in skips)
    assert any("ustc" in err and "unreachable" in err for err in skips)
    assert "mirrors.cloud.tencent.com" not in labels
    assert "mirrors.ustc.edu.cn" not in labels


def test_all_mirrors_failed_enriches_error_with_install_detail() -> None:
    result = _all_mirrors_failed(
        [
            "mirrors.example: missing_version 1.0.1",
            "pypi.org: Could not find a version that satisfies the requirement",
        ]
    )
    assert result.success is False
    assert result.error is not None
    assert result.error.startswith("upgrade failed on all mirrors")
    assert "Could not find" in result.error
    assert "missing_version" not in (result.error or "")


def test_run_managed_upgrade_uses_ranked_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.infra.setup import self_update

    monkeypatch.delenv("OCTOP_FPK_SITE_PACKAGES", raising=False)
    monkeypatch.setattr(self_update, "detect_installer", lambda: "uv")
    monkeypatch.setattr(self_update, "resolve_venv_python", lambda: "/venv/bin/python")
    monkeypatch.setattr(self_update, "get_local_version", lambda: "1.0.0")
    monkeypatch.setattr(
        self_update,
        "rank_install_indexes",
        lambda version, probe_timeout=8: (
            [
                ("https://fast.example/simple", "fast.example"),
                ("https://pypi.org/simple", "pypi.org"),
            ],
            ["slow.example: missing_version 1.0.1"],
        ),
    )
    calls: list[str] = []

    def fake_install(
        cmd: list[str],
        label: str,
        *,
        verbose: bool,
        timeout: float,
    ) -> tuple[int | None, str]:
        calls.append(label)
        assert timeout == self_update._INSTALL_TIMEOUT_S
        if label == "fast.example":
            return 1, "network reset"
        return 0, ""

    monkeypatch.setattr(self_update, "_run_install_cmd", fake_install)
    monkeypatch.setattr(
        self_update,
        "_verify_upgrade",
        lambda local, python, errs: UpgradeResult(
            success=True,
            installed_version="1.0.1",
            mirror_errors=errs,
        ),
    )

    result = self_update._run_managed_upgrade(version="1.0.1")
    assert result.success is True
    assert calls == ["fast.example", "pypi.org"]
    assert "slow.example: missing_version 1.0.1" in (result.mirror_errors or [])
    assert any("fast.example" in err for err in (result.mirror_errors or []))
