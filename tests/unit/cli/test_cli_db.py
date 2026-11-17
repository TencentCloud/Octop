"""Tests for offline CLI DB helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from octop.cli.main import cli
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.utils.paths import PathLayout
from octop.infra.utils.ulid import new_ulid


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def _bootstrap(fake_home: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["init", "--admin-username", "alice", "--admin-password", "TestPass12", "--yes"],
    )
    assert result.exit_code == 0, result.output


def test_list_agents_offline(fake_home: Path) -> None:
    _bootstrap(fake_home)
    paths = PathLayout(fake_home / ".octop")
    db = SqlitePool(paths.db)
    AgentRepo(db).create(agent_id="ag1", user_id=1, name="Bot")
    db.close()

    from octop.cli.support.db import list_agents_offline

    rows = list_agents_offline(as_user="alice")
    assert len(rows) == 1
    assert rows[0]["agent_id"] == "ag1"


def test_list_threads_offline(fake_home: Path) -> None:
    _bootstrap(fake_home)
    paths = PathLayout(fake_home / ".octop")
    db = SqlitePool(paths.db)
    AgentRepo(db).create(agent_id="ag1", user_id=1, name="Bot")
    tid = new_ulid()
    ThreadRepo(db).insert(
        thread_id=tid,
        agent_id="ag1",
        user_id=1,
        channel_type="dashboard",
        session_key="ag1:dashboard:1:dm",
        title="hello",
    )
    db.close()

    from octop.cli.support.db import list_threads_offline

    rows = list_threads_offline(agent_id="ag1", as_user="alice", limit=10)
    assert len(rows) == 1
    assert rows[0]["thread_id"] == tid
    assert rows[0]["has_messages"] is None


def test_agent_list_offline_flag(fake_home: Path) -> None:
    _bootstrap(fake_home)
    paths = PathLayout(fake_home / ".octop")
    db = SqlitePool(paths.db)
    AgentRepo(db).create(agent_id="ag1", user_id=1, name="Bot")
    db.close()

    runner = CliRunner()
    result = runner.invoke(cli, ["agent", "list", "--user", "alice"])
    assert result.exit_code == 0, result.output
    assert "ag1" in result.output


@pytest.fixture
def english_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("octop.cli.support.db.resolve_cli_locale", lambda: "en")
    monkeypatch.setenv("COLUMNS", "200")


@pytest.mark.usefixtures("english_cli")
def test_agent_list_shows_which_agents_run_on_the_global_model(fake_home: Path) -> None:
    _bootstrap(fake_home)
    paths = PathLayout(fake_home / ".octop")
    db = SqlitePool(paths.db)
    AgentRepo(db).create(agent_id="ag1", user_id=1, name="Bot")
    AgentRepo(db).create(agent_id="ag2", user_id=1, name="Coder", default_model="acme/big")
    db.close()
    runner = CliRunner()
    assert (
        runner.invoke(cli, ["models", "active", "--provider", "acme", "--model", "small"]).exit_code
        == 0
    )

    result = runner.invoke(cli, ["agent", "list", "--user", "alice"])
    assert result.exit_code == 0, result.output
    rows = {line.split("│")[1].strip(): line for line in result.output.splitlines() if "│" in line}
    assert "(global: acme/small)" in rows["ag1"]
    assert "acme/big" in rows["ag2"]
    assert "global" not in rows["ag2"]


@pytest.mark.usefixtures("english_cli")
def test_agent_list_says_when_no_model_is_set_anywhere(fake_home: Path) -> None:
    _bootstrap(fake_home)
    paths = PathLayout(fake_home / ".octop")
    db = SqlitePool(paths.db)
    AgentRepo(db).create(agent_id="ag1", user_id=1, name="Bot")
    db.close()

    result = CliRunner().invoke(cli, ["agent", "list", "--user", "alice"])
    assert result.exit_code == 0, result.output
    assert "(not set)" in result.output


@pytest.mark.usefixtures("english_cli")
def test_models_active_explains_an_unset_default(fake_home: Path) -> None:
    _bootstrap(fake_home)
    runner = CliRunner()

    unset = runner.invoke(cli, ["models", "active"])
    assert unset.exit_code == 0, unset.output
    assert unset.output.strip() != "/"
    assert "No global default model is set" in unset.output
    assert "octop models active --provider" in unset.output

    runner.invoke(cli, ["models", "active", "--provider", "acme", "--model", "small"])
    shown = runner.invoke(cli, ["models", "active"])
    assert shown.output.strip() == "acme / small"


# ── P0: _pg0param type-to-cast mapping ──────────────────────────────


@pytest.mark.parametrize(
    "col_type,expected",
    [
        ("REAL", "%s::double precision"),
        ("real", "%s::double precision"),
        ("FLOAT", "%s::double precision"),
        ("float", "%s::double precision"),
        ("DOUBLE", "%s::double precision"),
        ("double", "%s::double precision"),
        ("INTEGER", "%s::bigint"),
        ("integer", "%s::bigint"),
        ("INT", "%s::bigint"),
        ("int", "%s::bigint"),
        ("BIGINT", "%s::bigint"),
        ("bigint", "%s::bigint"),
        ("BLOB", "%s::bytea"),
        ("blob", "%s::bytea"),
        ("JSON", "%s::jsonb"),
        ("json", "%s::jsonb"),
        # unknown / fallback
        ("TEXT", "%s"),
        ("text", "%s"),
        ("VARCHAR", "%s"),
        ("BOOLEAN", "%s"),
        ("TIMESTAMP", "%s"),
        ("", "%s"),
    ],
)
def test_pg0param_returns_correct_cast(col_type: str, expected: str) -> None:
    from octop.cli.commands.db import _pg0param

    assert _pg0param(col_type) == expected


# ── P0: _convert_value type dispatch ──────────────────────────────────


class TestConvertValueNull:
    def test_none_is_none_regardless_of_type(self) -> None:
        from octop.cli.commands.db import _convert_value

        for t in ("INTEGER", "REAL", "TEXT", "BLOB", "JSON", "BOOLEAN", ""):
            assert _convert_value(None, t) is None


class TestConvertValueNumeric:
    def test_real_types_produce_float(self) -> None:
        from octop.cli.commands.db import _convert_value

        for t in ("REAL", "real", "FLOAT", "float", "DOUBLE", "double"):
            assert _convert_value(3.14, t) == 3.14
            assert isinstance(_convert_value(3.14, t), float)
            assert _convert_value(42, t) == 42.0
            assert isinstance(_convert_value(42, t), float)

    def test_integer_types_produce_int(self) -> None:
        from octop.cli.commands.db import _convert_value

        for t in ("INTEGER", "integer", "INT", "int", "BIGINT", "bigint"):
            assert _convert_value(42, t) == 42
            assert isinstance(_convert_value(42, t), int)
            assert _convert_value(0, t) == 0
            assert _convert_value(-1, t) == -1


class TestConvertValueBlob:
    def test_blob_produces_bytes(self) -> None:
        from octop.cli.commands.db import _convert_value

        result = _convert_value(b"hello", "BLOB")
        assert result == b"hello"
        assert isinstance(result, bytes)

    def test_blob_empty(self) -> None:
        from octop.cli.commands.db import _convert_value

        assert _convert_value(b"", "BLOB") == b""


class TestConvertValueJson:
    def test_json_string_roundtrips(self) -> None:
        from octop.cli.commands.db import _convert_value

        result = _convert_value('{"a":1}', "JSON")
        assert result == '{"a": 1}'
        import json

        json.loads(result)  # must be valid JSON

    def test_json_dict_is_serialised(self) -> None:
        from octop.cli.commands.db import _convert_value

        result = _convert_value({"key": [1, 2]}, "JSON")
        assert result == '{"key": [1, 2]}'

    def test_json_list_is_serialised(self) -> None:
        from octop.cli.commands.db import _convert_value

        result = _convert_value([1, "two", 3.0], "JSON")
        assert result == '[1, "two", 3.0]'

    def test_json_empty_string_yields_empty_array(self) -> None:
        from octop.cli.commands.db import _convert_value

        assert _convert_value("", "JSON") == "[]"

    def test_json_whitespace_string_passed_through(self) -> None:
        """Whitespace-only string is truthy, so the final fallback
        ``return str(val) if val else "[]"`` returns it as-is."""
        from octop.cli.commands.db import _convert_value

        assert _convert_value("  ", "JSON") == "  "

    def test_json_plain_string_raises_decode_error(self) -> None:
        """json.loads('hello') raises JSONDecodeError — the function
        does not catch this; callers must ensure only valid JSON strings
        are stored in JSON-typed columns."""
        import json

        from octop.cli.commands.db import _convert_value

        with pytest.raises(json.JSONDecodeError):
            _convert_value("hello", "JSON")


class TestConvertValueFallback:
    """When col_type is unknown, infer from Python value type."""

    def test_fallback_float_stays_float(self) -> None:
        from octop.cli.commands.db import _convert_value

        assert _convert_value(3.14, "TEXT") == 3.14

    def test_fallback_int_stays_int(self) -> None:
        from octop.cli.commands.db import _convert_value

        assert _convert_value(42, "VARCHAR") == 42

    def test_fallback_str_stays_str(self) -> None:
        from octop.cli.commands.db import _convert_value

        assert _convert_value("hello", "UNKNOWN") == "hello"
        assert _convert_value("你好", "") == "你好"

    def test_fallback_none_is_none(self) -> None:
        from octop.cli.commands.db import _convert_value

        assert _convert_value(None, "UNKNOWN") is None
