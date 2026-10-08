"""Native fnOS launchers must preserve wizard values without shell evaluation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

posix_only = pytest.mark.skipif(os.name != "posix", reason="bash launcher semantics")
pytestmark = posix_only
REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(params=["prepare", "run", "cli"])
def mode(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.fixture
def package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    app = tmp_path / "native package"
    for name in ("bin", "cmd", "var", "data/.octop"):
        (app / name).mkdir(parents=True, exist_ok=True)
    for name in ("octop", "octop-cli"):
        shutil.copyfile(REPO / "fnos/native/app/bin" / name, app / "bin" / name)
    # Use the packaged helpers, stubbing only host discovery and account checks.
    common = (REPO / "scripts/fnos/common.sh").read_text(encoding="utf-8")
    (app / "cmd/common.sh").write_text(
        common
        + """
find_python312() { printf '%s' "$OCTOP_TEST_PYTHON_STUB"; }
octop_assert_native_arch() { return 0; }
octop_prepend_fnos_node_path() { return 0; }
id() {
    if [ "${1:-}" = '-u' ]; then printf '1000'; else return 1; fi
}
""",
        encoding="utf-8",
    )
    stub = tmp_path / "python-stub"
    stub.write_text(
        '#!/bin/sh\nexec "$OCTOP_TEST_PYTHON" "$OCTOP_TEST_CAPTURE" "$@"\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    capture = tmp_path / "capture.py"
    capture.write_text(
        """
import json
import os
import sys
from pathlib import Path

if sys.argv[1:3] == ["-c", "import octop"]:
    sys.exit(0)
with open(os.environ["OCTOP_TEST_CALLS"], "a", encoding="utf-8") as output:
    output.write(json.dumps({
        "args": sys.argv[1:],
        "password": os.environ.get("OCTOP_DEFAULT_PASSWORD"),
        "display_name": os.environ.get("OCTOP_ADMIN_DISPLAY_NAME"),
        "port": os.environ.get("OCTOP_PORT"),
    }) + "\\n")
if sys.argv[1:4] == ["-m", "octop.cli.main", "init"]:
    (Path(os.environ["OCTOP_HOME"]) / "octop.db").touch()
""",
        encoding="utf-8",
    )
    for key, value in {
        "TRIM_APPDEST": str(app),
        "TRIM_PKGVAR": str(app / "var"),
        "TRIM_DATA_SHARE_PATHS": str(app / "data"),
        "OCTOP_HOME": str(app / "data/.octop"),
        "OCTOP_TEST_PYTHON_STUB": str(stub),
        "OCTOP_TEST_PYTHON": sys.executable,
        "OCTOP_TEST_CAPTURE": str(capture),
        "OCTOP_TEST_CALLS": str(app / "calls.jsonl"),
        "OCTOP_TEST_DEFINED": "must-not-expand",
    }.items():
        monkeypatch.setenv(key, value)
    for key in (
        "OCTOP_DEFAULT_PASSWORD",
        "OCTOP_ADMIN_USERNAME",
        "OCTOP_ADMIN_DISPLAY_NAME",
        "OCTOP_ADMIN_EMAIL",
        "OCTOP_PORT",
        "OCTOP_TEST_UNSET",
    ):
        monkeypatch.delenv(key, raising=False)
    return app


def run_launcher(package: Path, mode: str, env_text: str | None) -> list[dict]:
    if env_text is not None:
        (package / "var/.env").write_text(env_text, encoding="utf-8")
    if mode != "prepare":
        (package / "data/.octop/octop.db").touch()
    launcher = "octop-cli" if mode == "cli" else "octop"
    args = {"prepare": ["--prepare"], "run": [], "cli": ["version"]}[mode]
    result = subprocess.run(
        ["bash", str(package / "bin" / launcher), *args],
        cwd=package,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert not (package / "command-substitution").exists(), "Executed a password as shell code"
    assert result.returncode == 0, result.stderr
    return [
        json.loads(line)
        for line in (package / "calls.jsonl").read_text(encoding="utf-8").splitlines()
    ]


@pytest.mark.parametrize(
    "password",
    [
        pytest.param("ExamplePass9", id="ordinary"),
        pytest.param("Example9$OCTOP_TEST_UNSET", id="unset-variable"),
        pytest.param("Example9${OCTOP_TEST_DEFINED}", id="existing-variable"),
        pytest.param(" Example9 with spaces ", id="spaces"),
        pytest.param("Example9==value#fragment", id="equals-and-hash"),
        pytest.param("Example9$(touch command-substitution)", id="command-substitution"),
        pytest.param("Example9`touch command-substitution`", id="backticks"),
    ],
)
def test_password_is_loaded_literally(package: Path, mode: str, password: str) -> None:
    calls = run_launcher(
        package,
        mode,
        f"OCTOP_DEFAULT_PASSWORD={password}\nOCTOP_ADMIN_USERNAME=alice\nOCTOP_PORT=8099\n",
    )
    assert len(calls) == 1
    call = calls[0]
    assert call["password"] == password
    assert call["port"] == "8099"
    expected_command = {"prepare": "init", "run": "run", "cli": "version"}[mode]
    assert call["args"][:3] == ["-m", "octop.cli.main", expected_command]
    if mode == "prepare":
        args = call["args"]
        assert args[args.index("--admin-password") + 1] == password
        assert args[args.index("--admin-username") + 1] == "alice"
        assert (package / "data/.octop/.fnos-wizard-password-applied").exists()


def test_display_name_preserves_spaces_and_variables(package: Path, mode: str) -> None:
    display = "工程组 $OCTOP_TEST_DEFINED team"
    calls = run_launcher(
        package,
        mode,
        f"OCTOP_DEFAULT_PASSWORD=ExamplePass9\nOCTOP_ADMIN_DISPLAY_NAME={display}\n",
    )
    assert calls[0]["display_name"] == display
    if mode == "prepare":
        args = calls[0]["args"]
        assert args[args.index("--admin-display-name") + 1] == display


def test_ignores_non_assignment_lines_and_reads_final_unterminated_line(
    package: Path,
    mode: str,
) -> None:
    calls = run_launcher(
        package,
        mode,
        "# Wizard settings\n\nBAD KEY=value\n1BAD=value\n=value\n"
        "touch command-substitution\nOCTOP_PORT=8089\nOCTOP_PORT=8099\n"
        "OCTOP_DEFAULT_PASSWORD=ExamplePass9",
    )
    assert calls[0]["password"] == "ExamplePass9"
    assert calls[0]["port"] == "8099"


def test_missing_env_file_keeps_cli_usable(package: Path) -> None:
    calls = run_launcher(package, "cli", None)
    assert calls[0]["args"] == ["-m", "octop.cli.main", "version"]
    assert calls[0]["password"] is None
