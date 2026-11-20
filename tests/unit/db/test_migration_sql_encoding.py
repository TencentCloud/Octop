"""Repository SQL stays strict UTF-8 when the locale is not (issue #2869)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_SQL = Path(__file__).resolve().parents[3] / "src/octop/infra/db/migrations/001_initial.sql"
_PHRASE = "对应 Episode.id"
posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX locale categories")


def test_initial_migration_round_trips_as_utf8_not_legacy_code_pages() -> None:
    raw = _SQL.read_bytes()
    assert _PHRASE.encode("utf-8") in raw
    assert _PHRASE in raw.decode("utf-8")
    assert _PHRASE in _SQL.read_text(encoding="utf-8")
    # GitHub-hosted Windows is cp1252: the same bytes decode without raising.
    assert _PHRASE not in raw.decode("cp1252")
    with pytest.raises(UnicodeDecodeError, match=r"0x92") as caught:
        raw.decode("gbk")
    assert caught.value.encoding == "gbk"


@posix_only
def test_explicit_utf8_read_survives_pythonutf8_off(tmp_path: Path) -> None:
    """``PYTHONUTF8`` is a startup flag. A fresh C-locale interpreter still
    recovers the Chinese comment when the read names UTF-8."""
    script = tmp_path / "read_sql.py"
    script.write_text(
        "import locale\n"
        "import sys\n"
        "from pathlib import Path\n"
        "path = Path(sys.argv[1])\n"
        "print(locale.getencoding())\n"
        "try:\n"
        "    path.read_text()\n"
        "    print('IMPLICIT_OK')\n"
        "except UnicodeDecodeError:\n"
        "    print('IMPLICIT_FAIL')\n"
        "text = path.read_text(encoding='utf-8')\n"
        f"needle = {_PHRASE!r}\n"
        "print('PHRASE_OK' if needle in text else 'PHRASE_MISSING')\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONUTF8"] = "0"
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    env["LC_CTYPE"] = "C"
    result = subprocess.run(
        [sys.executable, str(script), str(_SQL)],
        capture_output=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    lines = result.stdout.decode("ascii").splitlines()
    assert lines[0].lower() in {"ansi_x3.4-1968", "us-ascii", "ascii", "c"}
    assert "IMPLICIT_FAIL" in lines
    assert "PHRASE_OK" in lines
    assert "PHRASE_MISSING" not in lines
