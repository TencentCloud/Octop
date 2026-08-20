"""CLI stdio encoding guard — emoji output must not crash on legacy code pages.

Reported on Chinese Windows (GBK / cp936): ``octop init`` bootstraps the
database and then raises ``UnicodeEncodeError`` while printing its ``✅``
success message, because piped/redirected stdout is encoded with the ANSI
code page. The CLI entry point now re-encodes stdout/stderr to UTF-8.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

from octop.cli.main import _ensure_utf8_stdio


def test_ensure_utf8_stdio_reconfigures_gbk_streams() -> None:
    out = io.TextIOWrapper(io.BytesIO(), encoding="gbk")
    err = io.TextIOWrapper(io.BytesIO(), encoding="gbk")
    _ensure_utf8_stdio(streams=(out, err))
    assert out.encoding.lower() == "utf-8"
    assert err.encoding.lower() == "utf-8"
    # U+2705 (✅) is not representable in GBK; must encode without raising.
    out.write("\u2705 Octop bootstrapped")
    out.flush()


def test_ensure_utf8_stdio_leaves_utf8_streams_alone() -> None:
    out = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    _ensure_utf8_stdio(streams=(out, None))
    assert out.encoding.lower() == "utf-8"


def test_init_completes_with_gbk_stdout(tmp_path: Path) -> None:
    """``octop init`` still bootstraps when stdout is forced to GBK. The crash
    previously happened at the final success message, after the DB and admin
    user were already created."""
    home = tmp_path / "octop-home"
    env = dict(os.environ)
    env["OCTOP_HOME"] = str(home)
    env["PYTHONIOENCODING"] = "gbk"
    env.pop("PYTHONUTF8", None)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "octop.cli.main",
            "init",
            "--yes",
            "--admin-username",
            "alice",
            "--admin-password",
            "Wonderland1",
        ],
        env=env,
        capture_output=True,
        check=False,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace") + proc.stderr.decode(
        "utf-8", "replace"
    )
    assert (home / "octop.db").is_file()
