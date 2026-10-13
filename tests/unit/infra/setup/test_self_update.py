"""Tests for octop.infra.setup.self_update."""

from __future__ import annotations

import json
import os
import sys
import zipfile
from pathlib import Path

import pytest

from octop.infra.setup.self_update import (
    UpgradeResult,
    _all_mirrors_failed,
    build_upgrade_command,
    fetch_pypi_info,
    index_label,
    is_newer,
    is_prerelease,
    page_has_package_version,
    parse_changelog_for_version,
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
    assert parse_version("1.0.2b5") > parse_version("1.0.2b4")
    assert parse_version("1.0.2b10") > parse_version("1.0.2b9")
    assert parse_version("1.0.2") > parse_version("1.0.2b5")
    assert parse_version("1.0.2+local.10") == parse_version("1.0.2")


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


def test_parse_changelog_for_beta_version() -> None:
    description = (
        "## [Unreleased]\n\n"
        "## [1.0.2b5] - 2026-09-29\n\n"
        "### 新增\n- remote bridge\n\n"
        "## [1.0.1] - 2026-09-21\n\n"
        "- stable only\n"
    )
    notes = parse_changelog_for_version(description, "1.0.2b5")
    assert notes is not None
    assert "remote bridge" in notes
    assert "stable only" not in notes


class _JsonResp:
    def __init__(self, payload: dict[str, object]) -> None:
        self._raw = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> _JsonResp:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_fetch_pypi_info_loads_prerelease_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = {
        "info": {"version": "1.0.1", "description": "## [1.0.1]\n- stable only\n"},
        "releases": {"1.0.1": [{}], "1.0.2b5": [{}]},
    }
    beta = {
        "info": {
            "version": "1.0.2b5",
            "description": "## [1.0.2b5]\n- remote bridge\n\n## [1.0.1]\n- stable\n",
        }
    }
    urls: list[str] = []

    def fake_urlopen(req: object, timeout: int = 10) -> _JsonResp:
        url = getattr(req, "full_url", "")
        urls.append(url)
        if url.endswith("/octop/json"):
            return _JsonResp(catalog)
        if url.endswith("/octop/1.0.2b5/json"):
            return _JsonResp(beta)
        raise AssertionError(url)

    monkeypatch.setattr("octop.infra.setup.self_update.urllib.request.urlopen", fake_urlopen)
    info = fetch_pypi_info()
    assert info is not None
    assert info.version == "1.0.2b5"
    assert info.latest_stable == "1.0.1"
    assert info.description is not None
    assert "remote bridge" in info.description
    assert any(url.endswith("/octop/1.0.2b5/json") for url in urls)


def test_fetch_pypi_info_skips_versioned_fetch_when_stable_is_latest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = {
        "info": {"version": "1.0.1", "description": "## [1.0.1]\n- stable\n"},
        "releases": {"1.0.1": [{}], "1.0.0": [{}]},
    }
    urls: list[str] = []

    def fake_urlopen(req: object, timeout: int = 10) -> _JsonResp:
        url = getattr(req, "full_url", "")
        urls.append(url)
        if url.endswith("/octop/json"):
            return _JsonResp(catalog)
        raise AssertionError(url)

    monkeypatch.setattr("octop.infra.setup.self_update.urllib.request.urlopen", fake_urlopen)
    info = fetch_pypi_info()
    assert info is not None
    assert info.version == "1.0.1"
    assert info.description is not None
    assert "stable" in info.description
    assert urls == ["https://pypi.org/pypi/octop/json"]


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


def test_portable_upgrade_prefers_bundled_uv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.infra.setup import self_update

    packages = tmp_path / "packages"
    executable = packages / "bin" / ("uv.exe" if os.name == "nt" else "uv")
    executable.parent.mkdir(parents=True)
    executable.write_text("bundled updater")
    executable.chmod(0o755)
    monkeypatch.setenv("OCTOP_GREEN_PACKAGES", str(packages))
    monkeypatch.setattr(self_update.shutil, "which", lambda _: "global-uv")

    assert self_update.detect_installer() == "uv"
    command = build_upgrade_command("uv", sys.executable, version="1.0.2b5")
    assert command is not None
    assert command[0] == str(executable)
    assert command[command.index("--target") + 1] == str(packages)
    assert "--upgrade-package" in command


def test_portable_without_bundled_uv_keeps_pip_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.infra.setup import self_update

    monkeypatch.setenv("OCTOP_GREEN_PACKAGES", str(tmp_path / "packages"))
    monkeypatch.setattr(self_update.shutil, "which", lambda _: None)
    monkeypatch.setattr(self_update, "_COMMON_UV_PATHS", [])
    assert self_update.detect_installer() == "pip"


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
    assert index_label("https://PyPI.org/simple") == "pypi.org"
    assert (
        index_label("https://mirrors.cloud.tencent.com/pypi/simple") == "mirrors.cloud.tencent.com"
    )
    assert index_label("https://notpypi.org/simple") == "notpypi.org"
    assert index_label("https://pypi.org.evil.example/simple") == "pypi.org.evil.example"
    assert index_label("https://pypi.org@evil.example/simple") == "evil.example"
    assert index_label("https://evil.example/simple?next=https://pypi.org") == "evil.example"


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
        lambda local, python, errs, **kwargs: UpgradeResult(
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


@pytest.mark.parametrize("has_metadata", [True, False])
def test_get_version_in_dir_does_not_use_other_installs(tmp_path: Path, has_metadata: bool) -> None:
    from octop.infra.setup import self_update

    if has_metadata:
        metadata = tmp_path / "octop-1.0.2b4.dist-info" / "METADATA"
        metadata.parent.mkdir()
        metadata.write_text("Name: octop\nVersion: 1.0.2b4\n", encoding="utf-8")

    assert self_update.get_version_in_dir(sys.executable, str(tmp_path)) is None


@pytest.mark.parametrize("target_env", ["OCTOP_GREEN_PACKAGES", "OCTOP_FPK_SITE_PACKAGES"])
@pytest.mark.parametrize(
    "versions",
    [
        ["1.0.2b4", "1.0.2b5"],
        ["0.9.33b4", "0.9.33b5", "0.9.33b6"],
        ["1.0.2b9", "1.0.2b10"],
        ["1.0.2b5", "1.0.2b4"],
    ],
)
def test_target_versions_load_package_despite_stale_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target_env: str, versions: list[str]
) -> None:
    from octop.infra.setup import self_update

    monkeypatch.delenv("OCTOP_GREEN_PACKAGES", raising=False)
    monkeypatch.delenv("OCTOP_FPK_SITE_PACKAGES", raising=False)
    monkeypatch.setenv(target_env, str(tmp_path))
    for version in versions:
        _write_octop_metadata(tmp_path, version)
    expected = max(versions, key=parse_version)
    _write_octop_package(tmp_path, expected)
    assert self_update.get_version_in_dir(sys.executable, str(tmp_path)) == expected
    assert self_update.get_local_version() == expected


def _write_octop_metadata(target: Path, version: str) -> None:
    metadata = target / f"octop-{version}.dist-info" / "METADATA"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(f"Name: octop\nVersion: {version}\n", encoding="utf-8")


def _write_octop_package(target: Path, version: str) -> None:
    package = target / "octop" / "__init__.py"
    package.parent.mkdir(exist_ok=True)
    package.write_text(f"__version__ = {version!r}\n", encoding="utf-8")
    (package.parent / "__main__.py").write_text(
        "import sys\nfrom . import __version__\n"
        "assert sys.argv[1:] == ['--version']\n"
        "print('octop v' + __version__)\nraise SystemExit(0)\n",
        encoding="utf-8",
    )


def _write_upgrade_wheel(directory: Path, metadata: str | None = None) -> Path:
    wheel = directory / "octop-1.0.2b5-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "octop-1.0.2b5.dist-info/METADATA", metadata or "Name: octop\nVersion: 1.0.2b5\n"
        )
    return wheel


@pytest.mark.parametrize("check_cli", [False, True])
def test_target_probe_ignores_import_and_pth_output(tmp_path: Path, check_cli: bool) -> None:
    from octop.infra.setup import self_update

    _write_octop_package(tmp_path, "1.0.2b5")
    (tmp_path / "noise.pth").write_text("import sys; print('pth output')\n", encoding="utf-8")
    with (tmp_path / "octop" / "__init__.py").open("a", encoding="utf-8") as output:
        output.write("print('import output', end='')\n")
    assert (
        self_update.get_version_in_dir(sys.executable, str(tmp_path), check_cli=check_cli)
        == "1.0.2b5"
    )


@pytest.mark.parametrize("broken_import", [False, True])
def test_new_metadata_cannot_hide_old_or_broken_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, broken_import: bool
) -> None:
    from octop.infra.setup import self_update

    monkeypatch.setenv("OCTOP_GREEN_PACKAGES", str(tmp_path))
    monkeypatch.setattr(self_update.time, "sleep", lambda _: None)
    _write_octop_metadata(tmp_path, "1.0.2b5")
    _write_octop_package(tmp_path, "1.0.2b4")
    if broken_import:
        (tmp_path / "octop" / "__init__.py").write_text(
            "raise ImportError('missing dependency')\n", encoding="utf-8"
        )
    result = self_update._verify_upgrade("1.0.2b4", sys.executable, [], version="1.0.2b5")
    assert not result.success
    assert result.installed_version == (None if broken_import else "1.0.2b4")


def test_target_version_loads_pth_dependencies(tmp_path: Path) -> None:
    from octop.infra.setup import self_update

    dependency = tmp_path / "dependencies"
    dependency.mkdir()
    (dependency / "upgrade_fixture_dep.py").write_text("VERSION = '1.0.2b5'\n", encoding="utf-8")
    (tmp_path / "dependencies.pth").write_text("dependencies\n", encoding="utf-8")
    _write_octop_package(tmp_path, "1.0.2b4")
    (tmp_path / "octop" / "__init__.py").write_text(
        "from upgrade_fixture_dep import VERSION as __version__\n", encoding="utf-8"
    )
    assert self_update.get_version_in_dir(sys.executable, str(tmp_path)) == "1.0.2b5"


def test_target_version_prevents_downgrade_before_service_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import octop
    from octop.infra.setup import self_update

    monkeypatch.setattr(octop, "__version__", "1.0.2b4")
    monkeypatch.setenv("OCTOP_GREEN_PACKAGES", str(tmp_path))
    _write_octop_package(tmp_path, "1.0.2b6")
    assert self_update.get_local_version() == "1.0.2b6"
    result = run_upgrade(version="1.0.2b5", locale="en")
    assert not result.success
    assert "1.0.2b6" in (result.error or "")


def test_target_verification_exercises_cli_instead_of_accepting_import_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.infra.setup import self_update

    monkeypatch.setenv("OCTOP_GREEN_PACKAGES", str(tmp_path))
    monkeypatch.setattr(self_update.time, "sleep", lambda _: None)
    _write_octop_package(tmp_path, "1.0.2b5")
    (tmp_path / "octop" / "__main__.py").write_text(
        "raise ImportError('CLI dependency unavailable')\n", encoding="utf-8"
    )
    assert self_update.get_version_in_dir(sys.executable, str(tmp_path)) == "1.0.2b5"
    result = self_update._verify_upgrade("1.0.2b4", sys.executable, [], version="1.0.2b5")
    assert not result.success


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ("compatible", True),
        ("missing", False),
        ("too-old", False),
        ("transitive-extra", False),
        ("inactive-marker", True),
        ("ambiguous", False),
        ("python-version", False),
        ("direct-url", False),
        ("installed-prerelease", True),
        ("prerelease-below-minimum", False),
    ],
)
def test_application_only_checks_target_dependency_closure(
    tmp_path: Path, scenario: str, expected: bool
) -> None:
    from octop.infra.setup import self_update

    def metadata(name: str, version: str, requires: list[str]) -> Path:
        path = tmp_path / f"{name}-{version}.dist-info" / "METADATA"
        path.parent.mkdir()
        path.write_text(
            f"Name: {name}\nVersion: {version}\n"
            + "".join(f"Requires-Dist: {requirement}\n" for requirement in requires),
            encoding="utf-8",
        )
        return path

    requirement = "upgrade-dep[feature]>=2.0"
    if scenario == "inactive-marker":
        requirement = "absent>=1; python_version < '0'"
    elif scenario == "direct-url":
        requirement = "upgrade-dep @ https://example.com/dep.whl"
    release = f"Name: octop\nVersion: 1.0.2b5\nRequires-Dist: {requirement}\n"
    metadata("octop", "1.0.2b4", ["old-absent-dep>=1"])
    if scenario != "missing":
        metadata(
            "upgrade_dep",
            "1.0"
            if scenario == "too-old"
            else "2.1b1"
            if scenario == "installed-prerelease"
            else "2.0b1"
            if scenario == "prerelease-below-minimum"
            else "2.0",
            ["absent>=1; extra == 'feature'"] if scenario == "transitive-extra" else [],
        )
    if scenario == "ambiguous":
        metadata("upgrade_dep", "2.1", [])
    if scenario == "python-version":
        release += "Requires-Python: >=100\n"
    wheel = _write_upgrade_wheel(tmp_path, release)
    assert (
        self_update._target_dependencies_satisfied(tmp_path, wheel, version="1.0.2b5") is expected
    )


@pytest.mark.parametrize(
    "metadata",
    [
        "Name: other\nVersion: 1.0.2b5\n",
        "Name: octop\nVersion: 1.0.2b6\n",
        "Name: octop\nVersion: broken\n",
        "Name: octop\n",
        "Name: octop\nVersion: 1.0.2b5\nVersion: 1.0.2b4\n",
    ],
)
def test_preflight_rejects_wrong_or_ambiguous_release(tmp_path: Path, metadata: str) -> None:
    from octop.infra.setup import self_update

    wheel = _write_upgrade_wheel(tmp_path, metadata)
    assert not self_update._target_dependencies_satisfied(tmp_path, wheel, version="1.0.2b5")


@pytest.mark.parametrize("broken", ["invalid-zip", "missing-metadata", "duplicate-metadata"])
def test_preflight_rejects_unreadable_wheel(tmp_path: Path, broken: str) -> None:
    from octop.infra.setup import self_update

    wheel = _write_upgrade_wheel(tmp_path)
    if broken == "invalid-zip":
        wheel.write_bytes(b"not a wheel")
    elif broken == "missing-metadata":
        with zipfile.ZipFile(wheel, "w"):
            pass
    else:
        with zipfile.ZipFile(wheel, "a") as archive:
            archive.writestr("other.dist-info/METADATA", "Name: octop\nVersion: 1.0.2b5\n")
    assert not self_update._target_dependencies_satisfied(tmp_path, wheel)


@pytest.mark.parametrize("failure", ["dependency", "cli", "version", "install"])
@pytest.mark.parametrize("full_install_success", [True, False])
def test_legacy_pip_fast_path_falls_back_and_verifies_full_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    full_install_success: bool,
) -> None:
    from octop.infra.setup import self_update

    monkeypatch.setenv("OCTOP_GREEN_PACKAGES", str(tmp_path))
    monkeypatch.setattr(self_update, "detect_installer", lambda: "pip")
    monkeypatch.setattr(self_update, "has_pip", lambda _: True)
    monkeypatch.setattr(self_update, "get_local_version", lambda: "1.0.2b4")
    monkeypatch.setattr(self_update.time, "sleep", lambda _: None)
    monkeypatch.setattr(self_update.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(
        self_update, "rank_install_indexes", lambda _: ([("https://one.example", "one")], [])
    )
    _write_octop_package(tmp_path, "1.0.2b4")
    _write_octop_metadata(tmp_path, "1.0.2b4")
    original = (tmp_path / "octop" / "__init__.py").read_bytes()
    calls: list[tuple[str, float]] = []
    downloads: list[Path] = []

    def install(cmd: list[str], label: str, *, timeout: float, **kwargs: object) -> tuple[int, str]:
        if "download" in cmd:
            calls.append(("download", timeout))
            directory = Path(cmd[cmd.index("--dest") + 1])
            downloads.append(directory)
            release = "Name: octop\nVersion: 1.0.2b5\n"
            if failure == "dependency":
                release += "Requires-Dist: missing-upgrade-dependency>=1\n"
            _write_upgrade_wheel(directory, release)
            return 0, ""
        fast = "--no-deps" in cmd
        calls.append(("fast" if fast else "full", timeout))
        if failure == "dependency":
            assert not fast
            assert (tmp_path / "octop" / "__init__.py").read_bytes() == original
        if fast and failure == "install":
            return 1, "local wheel install failed"
        if not fast and not full_install_success:
            return 1, "dependency install failed"
        version = "1.0.2b4" if fast and failure == "version" else "1.0.2b5"
        _write_octop_package(tmp_path, version)
        if fast and failure == "cli":
            (tmp_path / "octop" / "__main__.py").write_text(
                "raise ImportError('missing CLI dependency')\n", encoding="utf-8"
            )
        return 0, ""

    monkeypatch.setattr(self_update, "_run_install_cmd", install)
    result = self_update._run_managed_upgrade(version="1.0.2b5", locale="en")
    assert calls == (
        [("download", 90), ("full", 900)]
        if failure == "dependency"
        else [("download", 90), ("fast", 90), ("full", 900)]
    )
    assert result.success is full_install_success
    assert all(not directory.exists() for directory in downloads)
    if failure == "dependency" and not full_install_success:
        assert (tmp_path / "octop" / "__init__.py").read_bytes() == original
        assert (
            self_update.get_version_in_dir(sys.executable, str(tmp_path), check_cli=True)
            == "1.0.2b4"
        )


@pytest.mark.parametrize(
    ("actual", "requested", "success"),
    [
        ("1.0.2b5", "1.0.2b5", True),
        ("1.0.2-beta.5", "1.0.2b5", True),
        ("1.0.2b4", "1.0.2b5", False),
        ("1.0.2b6", "1.0.2b5", False),
        (None, "1.0.2b5", False),
        ("1.0.2b4", None, False),
        ("1.0.2b3", None, False),
        ("1.0.2b5", None, True),
    ],
)
def test_verify_upgrade_requires_newer_requested_version(
    monkeypatch: pytest.MonkeyPatch,
    actual: str | None,
    requested: str | None,
    success: bool,
) -> None:
    from octop.infra.setup import self_update

    monkeypatch.delenv("OCTOP_GREEN_PACKAGES", raising=False)
    monkeypatch.setattr(self_update, "get_installed_version", lambda _: actual)
    monkeypatch.setattr(self_update.time, "sleep", lambda _: None)
    result = self_update._verify_upgrade(
        "1.0.2b4", sys.executable, ["mirror: timeout"], version=requested, locale="en"
    )
    assert result.success is success
    assert result.installed_version == actual
    assert result.mirror_errors == ["mirror: timeout"]
    assert bool(result.error) is not success


@pytest.mark.parametrize("locale", ["en", "zh"])
def test_verify_green_upgrade_reads_only_target(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, locale: str
) -> None:
    from octop.i18n import tr
    from octop.infra.setup import self_update

    monkeypatch.setenv("OCTOP_GREEN_PACKAGES", str(tmp_path))
    monkeypatch.setattr(self_update.time, "sleep", lambda _: None)

    def unexpected_global_read(_: str) -> str:
        pytest.fail("portable verification must not read the interpreter's other installs")

    monkeypatch.setattr(self_update, "get_installed_version", unexpected_global_read)
    missing = self_update._verify_upgrade(
        "1.0.2b4", sys.executable, [], version="1.0.2b5", locale=locale
    )
    assert not missing.success
    assert missing.error == tr("update.version_unavailable", locale)

    _write_octop_metadata(tmp_path, "1.0.2b4")
    _write_octop_package(tmp_path, "1.0.2b4")
    unchanged = self_update._verify_upgrade(
        "1.0.2b4", sys.executable, [], version="1.0.2b5", locale=locale
    )
    assert not unchanged.success
    assert unchanged.installed_version == "1.0.2b4"

    metadata = tmp_path / "octop-1.0.2b5.dist-info" / "METADATA"
    metadata.parent.mkdir()
    metadata.write_text("Name: octop\nVersion: 1.0.2b5\n", encoding="utf-8")
    _write_octop_package(tmp_path, "1.0.2b5")
    installed = self_update._verify_upgrade("1.0.2b4", sys.executable, [], version="1.0.2b5")
    assert installed.success
    assert installed.installed_version == "1.0.2b5"


def test_pip_target_upgrade_with_stale_metadata_succeeds_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.infra.setup import self_update

    monkeypatch.setenv("OCTOP_GREEN_PACKAGES", str(tmp_path))
    monkeypatch.delenv("OCTOP_FPK_SITE_PACKAGES", raising=False)
    _write_octop_metadata(tmp_path, "1.0.2b4")
    _write_octop_package(tmp_path, "1.0.2b4")
    monkeypatch.setattr(self_update, "detect_installer", lambda: "pip")
    monkeypatch.setattr(self_update, "has_pip", lambda _: True)
    monkeypatch.setattr(self_update, "stash_console_scripts", lambda _: [])
    monkeypatch.setattr(
        self_update,
        "rank_install_indexes",
        lambda _: ([("https://one.example", "one"), ("https://two.example", "two")], []),
    )
    calls: list[str] = []
    downloads: list[Path] = []
    elapsed = 0.0
    monkeypatch.setattr(self_update.time, "monotonic", lambda: elapsed)

    def install(cmd: list[str], label: str, **kwargs: object) -> tuple[int, str]:
        nonlocal elapsed
        if "download" in cmd:
            assert kwargs["timeout"] == 90
            assert "--no-deps" in cmd and "--only-binary=:all:" in cmd
            assert "--pre" in cmd and cmd[-1] == "octop==1.0.2b5"
            assert self_update.get_local_version() == "1.0.2b4"
            directory = Path(cmd[cmd.index("--dest") + 1])
            downloads.append(directory)
            _write_upgrade_wheel(directory)
            elapsed = 80.0
            return 0, ""
        assert kwargs["timeout"] == 90
        assert cmd[:4] == [sys.executable, "-m", "pip", "install"]
        assert cmd[cmd.index("--target") + 1] == str(tmp_path)
        assert "--no-index" in cmd and "--no-deps" in cmd
        assert Path(cmd[-1]) == downloads[0] / "octop-1.0.2b5-py3-none-any.whl"
        calls.append(label)
        _write_octop_metadata(tmp_path, "1.0.2b5")
        _write_octop_package(tmp_path, "1.0.2b5")
        return 0, ""

    monkeypatch.setattr(self_update, "_run_install_cmd", install)
    result = run_upgrade(version="1.0.2b5", allow_prerelease=True)
    assert result.success
    assert result.installed_version == "1.0.2b5"
    assert calls == ["one"]
    assert all(not directory.exists() for directory in downloads)
    assert self_update.get_local_version() == "1.0.2b5"


def test_application_download_failure_retries_without_modifying_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.infra.setup import self_update

    monkeypatch.setenv("OCTOP_GREEN_PACKAGES", str(tmp_path))
    monkeypatch.setattr(self_update, "detect_installer", lambda: "pip")
    monkeypatch.setattr(self_update, "has_pip", lambda _: True)
    _write_octop_package(tmp_path, "1.0.2b4")
    monkeypatch.setattr(
        self_update,
        "rank_install_indexes",
        lambda _: ([("https://one.example", "one"), ("https://two.example", "two")], []),
    )
    downloads: list[Path] = []
    calls: list[str] = []

    def download(cmd: list[str], label: str, **kwargs: object) -> tuple[int, str]:
        assert "download" in cmd
        downloads.append(Path(cmd[cmd.index("--dest") + 1]))
        calls.append(label)
        return 1, "download failed"

    monkeypatch.setattr(self_update, "_run_install_cmd", download)
    result = self_update._run_managed_upgrade(version="1.0.2b5", locale="en")
    assert not result.success
    assert calls == ["one", "two"]
    assert all(not directory.exists() for directory in downloads)
    assert (
        self_update.get_version_in_dir(sys.executable, str(tmp_path), check_cli=True) == "1.0.2b4"
    )


@pytest.mark.parametrize("exhaust_during_download", [False, True])
def test_legacy_pip_fallback_window_is_shared_across_mirrors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exhaust_during_download: bool
) -> None:
    from octop.infra.setup import self_update

    monkeypatch.setenv("OCTOP_GREEN_PACKAGES", str(tmp_path))
    monkeypatch.setattr(self_update, "detect_installer", lambda: "pip")
    monkeypatch.setattr(self_update, "has_pip", lambda _: True)
    _write_octop_package(tmp_path, "1.0.2b4")
    original = (tmp_path / "octop" / "__init__.py").read_bytes()
    monkeypatch.setattr(
        self_update,
        "rank_install_indexes",
        lambda _: (
            [(f"https://{label}.example", label) for label in ("one", "two", "three")],
            [],
        ),
    )
    elapsed = 0.0
    monkeypatch.setattr(self_update.time, "monotonic", lambda: elapsed)
    calls: list[tuple[str, str, float]] = []

    def install(cmd: list[str], label: str, *, timeout: float, **kwargs: object) -> tuple[int, str]:
        nonlocal elapsed
        downloading = "download" in cmd
        calls.append((label, "download" if downloading else "full", timeout))
        if downloading:
            if label == "two" and exhaust_during_download:
                elapsed += timeout
                return 1, "download timed out"
            elapsed += 80
            _write_upgrade_wheel(
                Path(cmd[cmd.index("--dest") + 1]),
                "Name: octop\nVersion: 1.0.2b5\nRequires-Dist: missing-upgrade-dependency>=1\n",
            )
            return 0, ""
        assert "--no-deps" not in cmd
        elapsed += (890 if exhaust_during_download else 600) if label == "one" else timeout
        return 1, "dependency installation failed"

    monkeypatch.setattr(self_update, "_run_install_cmd", install)
    result = self_update._run_managed_upgrade(version="1.0.2b5", locale="en")
    assert not result.success
    assert calls == (
        [("one", "download", 90), ("one", "full", 900), ("two", "download", 10)]
        if exhaust_during_download
        else [
            ("one", "download", 90),
            ("one", "full", 900),
            ("two", "download", 90),
            ("two", "full", 220),
        ]
    )
    assert elapsed == 980  # The first download precedes the single 900-second window.
    assert (tmp_path / "octop" / "__init__.py").read_bytes() == original
    assert (
        self_update.get_version_in_dir(sys.executable, str(tmp_path), check_cli=True) == "1.0.2b4"
    )


@pytest.mark.parametrize("locale", ["en", "zh"])
@pytest.mark.parametrize("actual", [None, "1.0.2b4", "1.0.2b3", "1.0.2b5", "1.0.2b6"])
def test_fpk_verification_uses_target_and_rejects_missing_or_wrong_versions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, locale: str, actual: str | None
) -> None:
    from octop.i18n import tr
    from octop.infra.setup import self_update

    monkeypatch.setattr(self_update.time, "sleep", lambda _: None)
    if actual:
        _write_octop_metadata(tmp_path, actual)
        _write_octop_package(tmp_path, actual)
    if actual == "1.0.2b5":
        _write_octop_metadata(tmp_path, "1.0.2b4")
    result = self_update._verify_fpk_upgrade(
        "1.0.2b4", str(tmp_path), sys.executable, [], version="1.0.2b5", locale=locale
    )
    assert result.success is (actual == "1.0.2b5")
    assert result.installed_version == actual
    if result.success:
        assert result.message == tr("update.fpk_completed", locale, version=actual)
    elif actual is None:
        assert result.error == tr("update.version_unavailable", locale)
    else:
        assert result.error == tr(
            "update.version_mismatch", locale, actual=actual, expected="1.0.2b5"
        )


@pytest.mark.parametrize("locale", ["en", "zh"])
@pytest.mark.parametrize("fpk", [False, True])
@pytest.mark.parametrize("actual", ["1.0.2b5", "1.0.2b6"])
def test_upgrade_keeps_locale_bundle_when_installer_replaces_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, locale: str, fpk: bool, actual: str
) -> None:
    from octop.i18n import loader
    from octop.infra.setup import self_update

    bundles = tmp_path / "i18n"
    bundles.mkdir()
    original = {}
    for language in ("en", "zh"):
        content = (
            loader.resources.files("octop.i18n")
            .joinpath(f"{language}.json")
            .read_text(encoding="utf-8")
        )
        original[language] = json.loads(content)
        (bundles / f"{language}.json").write_text(content, encoding="utf-8")
    target = tmp_path / "packages"
    target.mkdir()
    monkeypatch.setenv("OCTOP_GREEN_PACKAGES", str(target))
    monkeypatch.setenv("OCTOP_FPK_SITE_PACKAGES", str(target) if fpk else "")
    monkeypatch.setattr(loader.resources, "files", lambda _: bundles)
    monkeypatch.setattr(self_update, "get_local_version", lambda: "1.0.2b4")
    monkeypatch.setattr(self_update, "get_version_in_dir", lambda *args, **kwargs: actual)
    monkeypatch.setattr(self_update, "detect_installer", lambda: "uv")
    monkeypatch.setattr(self_update, "find_uv_executable", lambda: str(tmp_path / "uv"))
    monkeypatch.setattr(self_update, "stash_console_scripts", lambda _: [])
    monkeypatch.setattr(self_update.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        self_update, "rank_install_indexes", lambda _: ([("https://one.example", "one")], [])
    )

    def install(*args: object, **kwargs: object) -> tuple[int, str]:
        for language in ("en", "zh"):
            replacement = dict(original[language])
            replacement.pop("update")
            (bundles / f"{language}.json").write_text(json.dumps(replacement), encoding="utf-8")
        return 0, ""

    monkeypatch.setattr(self_update, "_run_install_cmd", install)
    loader._load_all.cache_clear()
    try:
        result = run_upgrade(version="1.0.2b5", locale=locale)
        assert "update" not in json.loads((bundles / f"{locale}.json").read_text(encoding="utf-8"))
        assert result.success is (actual == "1.0.2b5")
        messages = original[locale]["update"]
        if result.success:
            assert result.installed_version == actual
            key = "fpk_completed" if fpk else "completed"
            assert result.message == messages[key].format(version=actual)
        else:
            assert (
                messages["version_mismatch"].format(actual=actual, expected="1.0.2b5")
                in (result.mirror_errors[0])
            )
    finally:
        loader._load_all.cache_clear()


@pytest.mark.parametrize("locale", ["en", "zh"])
@pytest.mark.parametrize("target", ["1.0.2b4", "1.0.2b3"])
@pytest.mark.parametrize("fpk", [True, False])
def test_run_upgrade_rejects_non_newer_target_before_changes(
    monkeypatch: pytest.MonkeyPatch, locale: str, target: str, fpk: bool
) -> None:
    from octop.i18n import tr
    from octop.infra.setup import self_update

    monkeypatch.setenv("OCTOP_FPK_SITE_PACKAGES", "fpk-target" if fpk else "")
    monkeypatch.setattr(self_update, "get_local_version", lambda: "1.0.2b4")

    def unexpected(*args: object, **kwargs: object) -> None:
        pytest.fail("non-newer target must be rejected before probing or modifying files")

    monkeypatch.setattr(self_update, "stash_console_scripts", unexpected)
    monkeypatch.setattr(self_update, "rank_install_indexes", unexpected)
    monkeypatch.setattr(self_update, "_run_install_cmd", unexpected)
    result = run_upgrade(version=target, locale=locale)
    assert not result.success
    assert result.error == tr(
        "errors.UPDATE_TARGET_NOT_NEWER", locale, target=target, current="1.0.2b4"
    )


def test_run_managed_upgrade_retries_after_failed_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.infra.setup import self_update

    monkeypatch.delenv("OCTOP_GREEN_PACKAGES", raising=False)
    monkeypatch.setattr(self_update, "detect_installer", lambda: "uv")
    monkeypatch.setattr(self_update, "get_local_version", lambda: "1.0.2b4")
    monkeypatch.setattr(self_update.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        self_update,
        "rank_install_indexes",
        lambda _: ([("https://one.example", "one"), ("https://two.example", "two")], []),
    )
    installed = "1.0.2b4"
    calls: list[str] = []

    def install(cmd: list[str], label: str, **kwargs: object) -> tuple[int, str]:
        nonlocal installed
        calls.append(label)
        if label == "two":
            installed = "1.0.2b5"
        return 0, ""

    monkeypatch.setattr(self_update, "_run_install_cmd", install)
    monkeypatch.setattr(self_update, "get_installed_version", lambda _: installed)
    result = self_update._run_managed_upgrade(version="1.0.2b5", locale="en")
    assert result.success
    assert calls == ["one", "two"]
    assert any("one:" in error and "1.0.2b4" in error for error in result.mirror_errors)


@pytest.mark.parametrize("portable", [False, True])
@pytest.mark.parametrize("installer", ["pip", "uv"])
def test_cold_target_install_budget_preserves_regular_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, portable: bool, installer: str
) -> None:
    from octop.infra.setup import self_update

    monkeypatch.setenv("OCTOP_GREEN_PACKAGES", str(tmp_path) if portable else "")
    monkeypatch.setattr(self_update, "detect_installer", lambda: installer)
    monkeypatch.setattr(self_update, "has_pip", lambda _: True)
    monkeypatch.setattr(self_update, "get_local_version", lambda: "1.0.2b4")
    monkeypatch.setattr(self_update, "get_installed_version", lambda _: "1.0.2b5")
    monkeypatch.setattr(self_update, "get_version_in_dir", lambda *args, **kwargs: "1.0.2b5")
    monkeypatch.setattr(
        self_update,
        "rank_install_indexes",
        lambda _: ([("https://one.example", "one")], []),
    )
    budgets: list[float] = []

    def cold_install(
        cmd: list[str], label: str, *, timeout: float, **kwargs: object
    ) -> tuple[int, str]:
        budgets.append(timeout)
        if "download" in cmd:
            _write_upgrade_wheel(
                Path(cmd[cmd.index("--dest") + 1]),
                "Name: octop\nVersion: 1.0.2b5\nRequires-Dist: absent>=1\n",
            )
        return (
            (0, "")
            if "--no-deps" in cmd or timeout >= 120
            else (1, "cold dependency install timed out")
        )

    monkeypatch.setattr(self_update, "_run_install_cmd", cold_install)
    result = self_update._run_managed_upgrade(version="1.0.2b5", locale="en")
    assert result.success is (portable and installer == "pip")
    assert budgets == ([90, 900] if portable and installer == "pip" else [90])


# The desktop launcher compares versions with its own Go implementation
# (desktop/src/download_test.go, TestCompareVersions) and decides whether to
# replace the portable runtime; the server decides below whether an upgrade is
# newer. The two ends must agree on the same strings, so this table mirrors the
# desktop one, including ignoring PEP 440 local segments on both ends.
_DESKTOP_ORDERING_PARITY = [
    ("0.9.32", "0.9.31", 1),
    ("0.9.32", "0.9.32", 0),
    ("0.9.31", "0.9.32", -1),
    ("0.9.32rc1", "0.9.31", 1),
    ("1.0", "1.0.0", 0),
    ("0.9.34-beta.1", "0.9.34b1", 0),
    ("1.0.2b4", "1.0.2b5", -1),
    ("1.0.2b5", "1.0.2b4", 1),
    ("1.0.2b10", "1.0.2b9", 1),
    ("1.0.2b5", "1.0.2b5", 0),
    ("1.0.2", "1.0.2b5", 1),
    ("1.0.2b5", "1.0.2", -1),
    ("1.0.2a2", "1.0.2b1", -1),
    ("1.0.2b5", "1.0.2rc1", -1),
    ("1.0.2rc1", "1.0.2", -1),
    ("1.0.2.dev1", "1.0.2a1", -1),
    ("1.0.2b5.dev1", "1.0.2b5", -1),
    ("1.0.2.post1", "1.0.2", 1),
    ("1!1.0.0", "2.0.0", 1),
    ("v1.0.2B05", "1.0.2b5", 0),
    ("1.0.2+local.10", "1.0.2+local.9", 0),
    ("1.0.2+local.10", "1.0.2", 0),
    ("1.0.2-custom", "1.0.1", 1),
    ("dev", "dev", 0),
]


@pytest.mark.parametrize(("left", "right", "want"), _DESKTOP_ORDERING_PARITY)
def test_version_ordering_matches_desktop_comparator(left: str, right: str, want: int) -> None:
    left_key, right_key = parse_version(left), parse_version(right)
    sign = (left_key > right_key) - (left_key < right_key)
    assert sign == want, f"{left} vs {right}: server={sign}, desktop={want}"
