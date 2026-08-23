"""tests/unit/test_env_file.py"""

from __future__ import annotations

from pathlib import Path

from octop.infra.utils.env_file import (
    apply_env_file,
    apply_env_file_replace,
    format_env_file,
    load_env_file,
    parse_env_text,
    save_env_file,
    search_env_changed,
)


def test_parse_and_roundtrip() -> None:
    text = '# comment\nFOO=bar\nexport BAZ="hello world"\nEMPTY=\n'
    parsed = parse_env_text(text)
    assert parsed == {"FOO": "bar", "BAZ": "hello world", "EMPTY": ""}
    assert format_env_file(parsed).splitlines() == [
        'BAZ="hello world"',
        "EMPTY=",
        "FOO=bar",
    ]


def test_save_and_load(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "env"
    save_env_file(path, {"API_KEY": "secret", "COUNT": "1"})
    assert load_env_file(path)["API_KEY"] == "secret"
    monkeypatch.delenv("API_KEY", raising=False)
    apply_env_file(path)
    import os

    assert os.environ["API_KEY"] == "secret"


def test_apply_env_file_replace_unsets_removed_keys(tmp_path: Path, monkeypatch) -> None:
    import os

    path = tmp_path / "env"
    save_env_file(path, {"KEEP": "1", "GONE": "2"})
    monkeypatch.setenv("GONE", "2")
    monkeypatch.setenv("KEEP", "1")
    monkeypatch.setenv("UNRELATED", "host")
    save_env_file(path, {"KEEP": "1"})
    apply_env_file_replace(path, previous={"KEEP": "1", "GONE": "2"})
    assert os.environ["KEEP"] == "1"
    assert "GONE" not in os.environ
    assert os.environ["UNRELATED"] == "host"


def test_overlay_stdio_spec_env_skips_protected() -> None:
    from octop.infra.utils.env_file import overlay_stdio_spec_env

    spec = overlay_stdio_spec_env(
        {"transport": "stdio", "command": "npx", "env": {"SPEC": "1"}},
        {"TAVILY_API_KEY": "tvly", "OCTOP_HOME": "/nope", "HOME": "/hack"},
    )
    assert spec["env"]["TAVILY_API_KEY"] == "tvly"
    assert spec["env"]["SPEC"] == "1"
    assert "OCTOP_HOME" not in spec["env"]
    assert "HOME" not in spec["env"]


def test_overlay_stdio_mcp_configs_applies_to_stdio_only() -> None:
    from octop.infra.utils.env_file import overlay_stdio_mcp_configs

    configs = overlay_stdio_mcp_configs(
        {
            "stdio_srv": {"transport": "stdio", "command": "npx"},
            "http_srv": {"transport": "http", "url": "http://localhost"},
        },
        {"MY_KEY": "secret"},
    )
    assert configs["stdio_srv"]["env"]["MY_KEY"] == "secret"
    assert "env" not in configs["http_srv"]


def test_search_env_changed_detects_tavily() -> None:
    assert search_env_changed({}, {"TAVILY_API_KEY": "x"}) is True
    assert search_env_changed({"FOO": "1"}, {"FOO": "2"}) is False
