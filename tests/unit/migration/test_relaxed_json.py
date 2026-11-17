"""The JSON5 subset OpenClaw configs are written in."""

from __future__ import annotations

import pytest

from octop.infra.migration import relaxed_json


def test_reads_plain_json() -> None:
    assert relaxed_json.loads('{"a": [1, 2.5, true, null, "x"]}') == {
        "a": [1, 2.5, True, None, "x"]
    }


def test_reads_comments_trailing_commas_and_bare_keys() -> None:
    text = """
    // line comment
    {
      gateway: { port: 18789, },   /* block
      comment */
      'single': 'it\\'s', "url": "https://example.com/a//b",
      list: [1, 2,],
      hex: 0x1F, negative: -3, exp: 1e3,
    }
    """
    assert relaxed_json.loads(text) == {
        "gateway": {"port": 18789},
        "single": "it's",
        "url": "https://example.com/a//b",
        "list": [1, 2],
        "hex": 31,
        "negative": -3,
        "exp": 1000.0,
    }


def test_decodes_escapes() -> None:
    assert relaxed_json.loads(r'"a\nb中\\"') == "a\nb中\\"


@pytest.mark.parametrize(
    "text",
    ['{"a": 1', '{"a" 1}', "[1 2]", '"open', "{a: 1} extra", "/* open", "{a: nope}"],
)
def test_rejects_broken_input(text: str) -> None:
    with pytest.raises(ValueError, match="at line"):
        relaxed_json.loads(text)


def test_error_names_the_line() -> None:
    with pytest.raises(ValueError, match="at line 3"):
        relaxed_json.loads('{\n  "a": 1,\n  "b" 2\n}')
