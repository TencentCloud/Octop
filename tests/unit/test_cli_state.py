"""tests/unit/test_cli_state.py"""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.cli.support.state import CLIState, load, save
from octop.infra.errors import ErrorCode, OctopError


def test_load_missing_returns_default(tmp_path: Path) -> None:
    state = load(tmp_path / "nope.json")
    assert state.default_user is None
    assert state.default_agent is None


def test_save_then_load_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    save(p, CLIState(default_user="alice", default_agent="a1"))
    out = load(p)
    assert out.default_user == "alice"
    assert out.default_agent == "a1"


def test_load_ignores_legacy_token_and_base_url(tmp_path: Path) -> None:
    p = tmp_path / "x.json"
    p.write_text(
        '{"base_url": "http://h:9", "token": "legacy", "default_user": "u", "default_agent": "a"}'
    )
    out = load(p)
    assert out.default_user == "u"
    assert out.default_agent == "a"


def test_load_corrupt_file_raises_typed_error(tmp_path: Path) -> None:
    """A torn ``cli_state.json`` must not reach the user as a bare traceback.

    Every CLI command reads this file (``config.py``, ``agent.py``, ``acting.py``,
    ``ctx.py``, ``db.py``, ``repl/runtime.py``), so a raw ``JSONDecodeError``
    escaping ``load`` takes down all of them at once.
    """
    p = tmp_path / "cli_state.json"
    p.write_text('{"default_user": "u",}', encoding="utf-8")  # trailing comma
    with pytest.raises(OctopError) as excinfo:
        load(p)
    assert excinfo.value.code is ErrorCode.CONFIG_FILE_CORRUPT


def test_load_non_object_raises_typed_error(tmp_path: Path) -> None:
    p = tmp_path / "cli_state.json"
    p.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(OctopError) as excinfo:
        load(p)
    assert excinfo.value.code is ErrorCode.CONFIG_FILE_CORRUPT


def test_save_is_atomic_so_a_torn_write_keeps_the_old_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``save`` must publish through ``os.replace``, never truncate in place.

    An interrupted write (crash, full disk) that truncates ``cli_state.json``
    creates exactly the corrupt file the two tests above then refuse to parse.
    """
    p = tmp_path / "cli_state.json"
    save(p, CLIState(default_user="alice", default_agent="a1"))
    original = p.read_text(encoding="utf-8")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("octop.infra.utils.json_file.os.replace", boom)
    with pytest.raises(OSError, match="disk full"):
        save(p, CLIState(default_user="bob", default_agent="b1"))
    assert p.read_text(encoding="utf-8") == original
    assert [q.name for q in tmp_path.iterdir()] == ["cli_state.json"]
