"""Unit tests for the shared JSON config helpers (issue #730)."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from octop.infra.utils.json_file import (
    JsonFileCorruptError,
    read_json_object,
    write_json_atomic,
)

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX file modes only")


def test_read_absent_file_returns_none(tmp_path: Path) -> None:
    assert read_json_object(tmp_path / "missing.json") is None


def test_read_valid_object(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"bind_host": "0.0.0.0", "port": 8088}), encoding="utf-8")
    assert read_json_object(path) == {"bind_host": "0.0.0.0", "port": 8088}


def test_read_corrupt_raises_with_position_and_never_leaks_contents(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    # Trailing comma — the classic hand-edit slip. The password must not surface.
    path.write_text('{"database": {"password": "s3cret"},}', encoding="utf-8")
    with pytest.raises(JsonFileCorruptError) as excinfo:
        read_json_object(path)
    err = excinfo.value
    assert err.path == path
    assert "line" in err.detail and "column" in err.detail
    assert "s3cret" not in err.detail
    assert "s3cret" not in str(err)


def test_read_non_object_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(JsonFileCorruptError) as excinfo:
        read_json_object(path)
    assert "list" in excinfo.value.detail


def test_write_is_pretty_newline_terminated_and_leaves_no_temp_files(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    write_json_atomic(path, {"a": 1})
    text = path.read_text(encoding="utf-8")
    assert json.loads(text) == {"a": 1}
    assert text.endswith("\n")
    assert [p.name for p in tmp_path.iterdir()] == ["config.json"]


def test_write_creates_missing_parent(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "config.json"
    write_json_atomic(path, {"a": 1})
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}


def test_failed_replace_leaves_original_intact_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A torn write must not be observable: the old file survives byte-for-byte."""
    path = tmp_path / "config.json"
    original = '{"bind_host": "0.0.0.0", "database": {"driver": "postgresql"}}'
    path.write_text(original, encoding="utf-8")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("octop.infra.utils.json_file.os.replace", boom)
    with pytest.raises(OSError, match="disk full"):
        write_json_atomic(path, {"port": 1})
    assert path.read_text(encoding="utf-8") == original
    assert [p.name for p in tmp_path.iterdir()] == ["config.json"]


@posix_only
def test_write_preserves_existing_file_mode(tmp_path: Path) -> None:
    """A config write must never silently change an existing file's mode."""
    path = tmp_path / "config.json"
    path.write_text("{}", encoding="utf-8")
    os.chmod(path, 0o640)
    write_json_atomic(path, {"a": 1})
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


@posix_only
def test_write_new_file_uses_umask_default_not_mkstemp_0600(tmp_path: Path) -> None:
    """mkstemp's 0600 must not leak into a new config.json.

    A root-created 0600 file would be unreadable to the service user after
    ``octop service start --scope system``; the two pre-existing config.json
    writers (``db/rebind.py``, ``backup/auto.py``) produce the umask default.
    """
    mask = os.umask(0o022)
    os.umask(mask)
    path = tmp_path / "fresh.json"
    write_json_atomic(path, {"a": 1})
    assert stat.S_IMODE(path.stat().st_mode) == 0o666 & ~mask


@posix_only
def test_native_partial_write_preserves_config_and_closes_temp(tmp_path: Path) -> None:
    """A genuine file-size cap makes the first raw write partially succeed."""
    path = tmp_path / "config.json"
    original = b'{"database": {"backend": "postgresql"}}'
    path.write_bytes(original)
    script = r"""import errno
import json
import os
import resource
import signal
import sys
from pathlib import Path
from octop.infra.utils import json_file
path = Path(sys.argv[1])
original = path.read_bytes()
created_fds = []
mkstemp = json_file.tempfile.mkstemp
def tracked_mkstemp(*args, **kwargs):
    fd, name = mkstemp(*args, **kwargs)
    created_fds.append(fd)
    return fd, name
json_file.tempfile.mkstemp = tracked_mkstemp
signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
resource.setrlimit(resource.RLIMIT_FSIZE, (128, 128))
data = {"database": {"backend": "postgresql"},
        "plugins": {f"plugin-{i}": {"enabled": True} for i in range(12)}}
try:
    json_file.write_json_atomic(path, data)
except OSError as exc:
    assert exc.errno == errno.EFBIG, exc
else:
    raise AssertionError("partial write was reported as a successful save")
assert path.read_bytes() == original
assert list(path.parent.iterdir()) == [path]
assert len(created_fds) == 1
try:
    os.fstat(created_fds[0])
except OSError as exc:
    assert exc.errno == errno.EBADF, exc
else:
    raise AssertionError("temporary descriptor was left open")
print("original bytes preserved; temporary file removed; descriptor closed")
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert path.read_bytes() == original
