"""Unit tests for the shared JSON config helpers (issue #730)."""

from __future__ import annotations

import json
import os
import stat
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from octop.infra.utils.json_file import (
    JsonFileCorruptError,
    read_json_object,
    update_json_object,
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


def test_update_json_object_creates_absent_file(tmp_path: Path) -> None:
    path = tmp_path / "config.json"

    def mutate(data: dict[str, Any]) -> None:
        data["plugins"] = {"echo-tool": {"enabled": True}}

    result = update_json_object(path, mutate)
    assert result == {"plugins": {"echo-tool": {"enabled": True}}}
    assert json.loads(path.read_text(encoding="utf-8")) == result


def test_update_json_object_never_mutates_a_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    original = '{"database": {"password": "s3cret"},}'
    path.write_text(original, encoding="utf-8")
    touched: list[bool] = []

    def mutate(data: dict[str, Any]) -> None:
        touched.append(True)

    with pytest.raises(JsonFileCorruptError):
        update_json_object(path, mutate)
    assert touched == []
    assert path.read_text(encoding="utf-8") == original


def test_update_json_object_serializes_concurrent_merges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two writers merging different keys must not drop either one.

    The delay after the read pins the interleaving: both threads finish reading
    the same snapshot before either writes — exactly what an unsynchronized
    read-modify-write does whenever a marketplace install and a dashboard
    toggle land together.
    """
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"database": {"driver": "postgresql"}}), encoding="utf-8")
    real_read = read_json_object

    def slow_read(target: Path) -> dict[str, Any] | None:
        data = real_read(target)
        time.sleep(0.02)
        return data

    monkeypatch.setattr("octop.infra.utils.json_file.read_json_object", slow_read)
    start = threading.Barrier(2)
    errors: list[BaseException] = []

    def worker(plugin_id: str, enabled: bool) -> None:
        try:
            start.wait(timeout=5)

            def mutate(data: dict[str, Any]) -> None:
                plugins = data.setdefault("plugins", {})
                plugins[plugin_id] = {"enabled": enabled}

            update_json_object(path, mutate)
        except BaseException as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=("alpha", True), daemon=True),
        threading.Thread(target=worker, args=("beta", False), daemon=True),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()

    assert errors == []
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["database"] == {"driver": "postgresql"}
    assert data["plugins"] == {"alpha": {"enabled": True}, "beta": {"enabled": False}}
