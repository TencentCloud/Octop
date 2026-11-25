"""Child-output decoding and upgrade import checks (issue #2869)."""

from __future__ import annotations

import importlib.util
import locale
import os
import subprocess
import sys
from pathlib import Path

import pytest

from octop.infra.setup import self_update

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX locale categories")


def _legacy_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(locale, "getencoding", lambda: "gbk")
    monkeypatch.setattr(locale, "getpreferredencoding", lambda _do_setlocale=False: "gbk")


def _write_octop_package(target: Path, version: str) -> None:
    package = target / "octop"
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text(f"__version__ = {version!r}\n", encoding="utf-8")
    (package / "__main__.py").write_text(
        "import sys\nfrom . import __version__\n"
        "assert sys.argv[1:] == ['--version']\n"
        "print('octop v' + __version__)\nraise SystemExit(0)\n",
        encoding="utf-8",
    )


def _write_critical_stubs(target: Path) -> None:
    for name in self_update._CRITICAL_MODULES:
        package = target / name
        package.mkdir(parents=True, exist_ok=True)
        (package / "__init__.py").write_text("# critical-import stub\n", encoding="utf-8")


def _venv_python(root: Path) -> Path:
    if os.name == "nt":
        return root / "Scripts" / "python.exe"
    return root / "bin" / "python"


def _gbk_text_child_env() -> dict[str, str]:
    """UTF-8 mode off, child text streams encoded as GBK.

    ``PYTHONIOENCODING`` selects the encoding ``print`` uses. That reproduces
    the bytes a GBK ANSI console would emit. It does not change the Windows
    ANSI code page, so this remains a simulation of that console.
    """
    env = os.environ.copy()
    env["PYTHONUTF8"] = "0"
    env["PYTHONIOENCODING"] = "gbk"
    return env


def _read_utf8_stdout(
    python: str,
    code: str,
    *args: str,
    env: dict[str, str] | None = None,
) -> str:
    """Decode stdout the child wrote as UTF-8 bytes.

    ``print`` follows the child's text encoding. A Chinese path printed with
    UTF-8 mode off and a GBK text encoding is not valid UTF-8.
    """
    result = subprocess.run(
        [python, "-c", code, *args],
        capture_output=True,
        check=False,
        env=env,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.decode("utf-8").strip()


def _read_purelib(python: str, *, env: dict[str, str] | None = None) -> Path:
    text = _read_utf8_stdout(
        python,
        "import sys, sysconfig; sys.stdout.buffer.write(sysconfig.get_path('purelib').encode('utf-8'))",
        env=env,
    )
    return Path(text)


def test_install_output_preserves_utf8_text_and_exit_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _legacy_locale(monkeypatch)
    command = [
        sys.executable,
        "-c",
        "import sys; sys.stderr.buffer.write('安装失败：中文'.encode()); raise SystemExit(2)",
    ]
    code, snippet = self_update._run_install_cmd(command, "mirror", verbose=False, timeout=30)
    assert code == 2
    assert "安装失败：中文" in snippet
    assert "ä¸­æ–‡" not in snippet


def test_install_output_keeps_exit_status_for_malformed_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _legacy_locale(monkeypatch)
    command = [
        sys.executable,
        "-c",
        "import sys; sys.stderr.buffer.write(bytes([98, 101, 102, 111, 114, 101, 255, 97, 102, 116, 101, 114])); raise SystemExit(5)",
    ]
    code, snippet = self_update._run_install_cmd(command, "mirror", verbose=False, timeout=30)
    assert code == 5
    assert "before" in snippet
    assert "after" in snippet


def test_install_timeout_and_verbose_keep_their_contracts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _legacy_locale(monkeypatch)
    code, snippet = self_update._run_install_cmd(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        "mirror",
        verbose=False,
        timeout=1,
    )
    assert code is None
    assert snippet == "timed out after 1s"

    code, snippet = self_update._run_install_cmd(
        [
            sys.executable,
            "-c",
            "import sys; sys.stderr.buffer.write('安装失败：中文'.encode()); raise SystemExit(4)",
        ],
        "mirror",
        verbose=True,
        timeout=30,
    )
    assert code == 4
    assert snippet == ""


def test_version_probe_ignores_utf8_noise_and_rejects_bad_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _legacy_locale(monkeypatch)
    _write_octop_package(tmp_path, "1.0.2b5")
    (tmp_path / "noise.pth").write_text(
        "import sys\nsys.stdout.buffer.write('路径噪声：中文\\n'.encode())\n",
        encoding="utf-8",
    )
    assert self_update.get_version_in_dir(sys.executable, str(tmp_path)) == "1.0.2b5"

    noise = "路径噪声：中文\n".encode()
    payload = noise + b'__OCTOP_PROBE__"1.0.2b5"'
    assert self_update._version_from_probe_stdout(payload) == "1.0.2b5"
    broken = b'__OCTOP_PROBE__"1.0.2b5\xff"'
    assert self_update._version_from_probe_stdout(broken) is None
    assert self_update._decode_version_stdout(b"1.0.2b5\xff") is None
    assert self_update._decode_version_stdout(b"1.0.2b5\n") == "1.0.2b5"


def _prepend_pythonpath(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    current = os.environ.get("PYTHONPATH")
    monkeypatch.setenv("PYTHONPATH", str(path) if not current else str(path) + os.pathsep + current)


def test_installed_version_survives_utf8_stderr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from importlib.metadata import version

    (tmp_path / "sitecustomize.py").write_text(
        "import sys\nsys.stderr.buffer.write('版本探测：中文\\n'.encode())\n",
        encoding="utf-8",
    )
    _prepend_pythonpath(monkeypatch, tmp_path)
    _legacy_locale(monkeypatch)
    expected = version("octop")
    assert "中文" not in expected
    assert self_update.get_installed_version(sys.executable) == expected


def test_has_pip_survives_utf8_stdout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    probe = subprocess.run(
        [sys.executable, "-m", "pip", "--version"],
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0:
        pytest.skip("pip is not installed for this interpreter")
    (tmp_path / "sitecustomize.py").write_text(
        "import sys\nsys.stdout.buffer.write('pip 探测：中文\\n'.encode())\n",
        encoding="utf-8",
    )
    _prepend_pythonpath(monkeypatch, tmp_path)
    _legacy_locale(monkeypatch)
    assert self_update.has_pip(sys.executable) is True


def test_target_upgrade_requires_critical_imports_in_that_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spec = importlib.util.find_spec("octop_harness")
    assert spec is not None and spec.origin is not None
    assert not Path(spec.origin).resolve().is_relative_to(tmp_path.resolve())
    monkeypatch.delenv("OCTOP_GREEN_PACKAGES", raising=False)
    monkeypatch.delenv("OCTOP_FPK_SITE_PACKAGES", raising=False)
    monkeypatch.setattr(self_update.time, "sleep", lambda _: None)
    _write_octop_package(tmp_path, "1.0.2b5")

    missing = self_update._verify_upgrade(
        "1.0.2b4",
        sys.executable,
        [],
        version="1.0.2b5",
        locale="en",
        target=tmp_path,
    )
    assert missing.success is False
    assert missing.installed_version == "1.0.2b5"
    assert missing.error is not None
    for name in self_update._CRITICAL_MODULES:
        assert name in missing.error

    _write_critical_stubs(tmp_path)
    installed = self_update._verify_upgrade(
        "1.0.2b4",
        sys.executable,
        [],
        version="1.0.2b5",
        locale="zh",
        target=tmp_path,
    )
    assert installed.success is True
    assert installed.installed_version == "1.0.2b5"
    assert installed.message is not None
    assert "1.0.2b5" in installed.message


def test_managed_upgrade_requires_critical_imports_in_that_interpreter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert importlib.util.find_spec("octop_harness") is not None
    venv = tmp_path / "中文环境" / "venv"
    created = subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(venv)],
        capture_output=True,
        check=False,
        timeout=120,
    )
    assert created.returncode == 0, created.stderr
    python = _venv_python(venv)
    # The child text encoding is GBK and UTF-8 mode is off. purelib is still
    # returned as UTF-8 bytes, including the Chinese directory.
    site_packages = _read_purelib(str(python), env=_gbk_text_child_env())
    assert site_packages.is_relative_to(venv)
    assert "中文环境" in str(site_packages)
    dist = site_packages / "octop-1.0.2b5.dist-info"
    dist.mkdir(parents=True)
    (dist / "METADATA").write_text("Name: octop\nVersion: 1.0.2b5\n", encoding="utf-8")
    monkeypatch.delenv("OCTOP_GREEN_PACKAGES", raising=False)
    monkeypatch.delenv("OCTOP_FPK_SITE_PACKAGES", raising=False)
    monkeypatch.delenv("PYTHONPATH", raising=False)
    monkeypatch.setattr(self_update.time, "sleep", lambda _: None)

    missing = self_update._verify_upgrade(
        "1.0.2b4", str(python), [], version="1.0.2b5", locale="en"
    )
    assert missing.success is False
    assert missing.installed_version == "1.0.2b5"
    assert missing.error is not None
    assert "octop_harness" in missing.error
    assert "octop_memory" in missing.error

    _write_critical_stubs(site_packages)
    installed = self_update._verify_upgrade(
        "1.0.2b4", str(python), [], version="1.0.2b5", locale="en"
    )
    assert installed.success is True
    assert installed.installed_version == "1.0.2b5"


def test_chinese_path_round_trips_when_child_text_encoding_is_gbk(tmp_path: Path) -> None:
    """``print`` under a GBK text encoding is not UTF-8.

    ``PYTHONIOENCODING=gbk`` with ``PYTHONUTF8=0`` simulates that console. The
    lookup used for a venv purelib writes UTF-8 bytes instead, so a Chinese
    path survives the parent decode.
    """
    root = tmp_path / "中文环境"
    root.mkdir()
    env = _gbk_text_child_env()
    printed = subprocess.run(
        [sys.executable, "-c", "import sys; print(sys.argv[1])", str(root)],
        capture_output=True,
        check=False,
        env=env,
    )
    assert printed.returncode == 0, printed.stderr
    with pytest.raises(UnicodeDecodeError):
        printed.stdout.decode("utf-8")
    assert "中文环境" in printed.stdout.decode("gbk")

    echoed = _read_utf8_stdout(
        sys.executable,
        "import sys; sys.stdout.buffer.write(sys.argv[1].encode('utf-8'))",
        str(root),
        env=env,
    )
    assert echoed == str(root)
    assert "中文环境" in echoed


def test_subprocess_text_mode_emits_encoding_warning(tmp_path: Path) -> None:
    script = tmp_path / "warn_text.py"
    script.write_text(
        "import subprocess\n"
        "import sys\n"
        "subprocess.run([sys.executable, '-c', 'print(1)'], capture_output=True, text=True, check=False)\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONWARNINGS"] = "error::EncodingWarning"
    result = subprocess.run(
        [sys.executable, "-X", "warn_default_encoding", str(script)],
        capture_output=True,
        check=False,
        env=env,
    )
    assert result.returncode != 0
    assert b"EncodingWarning" in result.stderr


def test_updater_capture_emits_no_encoding_warning(tmp_path: Path) -> None:
    script = tmp_path / "updater_capture.py"
    script.write_text(
        "import warnings\n"
        "warnings.simplefilter('error', EncodingWarning)\n"
        "import sys\n"
        "from octop.infra.setup.self_update import _run_install_cmd, get_installed_version\n"
        "code, snippet = _run_install_cmd(\n"
        "    [sys.executable, '-c', \"import sys; sys.stderr.buffer.write('安装失败：中文'.encode()); raise SystemExit(2)\"],\n"
        "    'probe', verbose=False, timeout=30,\n"
        ")\n"
        "assert code == 2, (code, snippet)\n"
        "assert '安装失败：中文' in snippet\n"
        "assert 'ä¸­æ–‡' not in snippet\n"
        "version = get_installed_version(sys.executable)\n"
        "assert version and '中文' not in version\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONWARNINGS"] = "error::EncodingWarning"
    result = subprocess.run(
        [
            sys.executable,
            "-X",
            "warn_default_encoding",
            "-W",
            "error::EncodingWarning",
            str(script),
        ],
        capture_output=True,
        check=False,
        env=env,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")


def test_pythonutf8_is_read_at_startup_only(monkeypatch: pytest.MonkeyPatch) -> None:
    before = sys.flags.utf8_mode
    monkeypatch.setenv("PYTHONUTF8", "0" if before else "1")
    assert sys.flags.utf8_mode == before
    env = os.environ.copy()
    env["PYTHONUTF8"] = "0"
    result = subprocess.run(
        [sys.executable, "-c", "import sys; print(sys.flags.utf8_mode)"],
        capture_output=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == b"0"


@posix_only
def test_pythonutf8_off_uses_the_c_locale_encoding() -> None:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "0"
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    env["LC_CTYPE"] = "C"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import locale, sys; print(sys.flags.utf8_mode); print(locale.getencoding())",
        ],
        capture_output=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    mode, encoding = result.stdout.decode("ascii").splitlines()
    assert mode == "0"
    assert encoding.lower() in {"ansi_x3.4-1968", "us-ascii", "ascii", "c"}
