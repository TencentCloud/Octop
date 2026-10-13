"""tests/unit/gateway/test_slash_parse.py"""

from __future__ import annotations

import pytest

from octop.infra.gateway.slash.parser import parse_slash


@pytest.mark.parametrize(
    ("text", "name", "args"),
    [
        ("/help", "help", ""),
        ("  /help  ", "help", ""),
        ("/HELP", "help", ""),
        ("/model openai:gpt-4o", "model", "openai:gpt-4o"),
        ("/new\nhello", "new", "hello"),
        ("/switch-thread t1", "switch-thread", "t1"),
    ],
)
def test_parses_commands(text: str, name: str, args: str) -> None:
    cmd = parse_slash(text)
    assert cmd is not None
    assert (cmd.name, cmd.args) == (name, args)


@pytest.mark.parametrize(
    "text",
    [
        "/root/ddd",
        "/root/ddd is missing",
        "/usr/bin/env python",
        "/etc/hosts",
        "/tmp/a.txt",
        "//comment",
        "/2fa",
        "/ help",
        "",
        None,
    ],
)
def test_rejects_paths_and_non_commands(text: str | None) -> None:
    assert parse_slash(text) is None
