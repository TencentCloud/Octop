"""Parse the JSON5 subset OpenClaw accepts in ``openclaw.json``.

Plain JSON plus comments, trailing commas, single-quoted strings and unquoted
keys. Not a general JSON5 implementation — just enough to read a config a
person may have edited by hand.
"""

from __future__ import annotations

import re
from typing import Any

_IDENTIFIER = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_NUMBER = re.compile(r"[+-]?(?:0[xX][0-9a-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "0": "\0"}
_LITERALS: dict[str, Any] = {"true": True, "false": False, "null": None}


def loads(text: str) -> Any:
    parser = _Parser(text)
    value = parser.value()
    parser.skip()
    if parser.pos != len(text):
        parser.fail("unexpected content")
    return value


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0

    def fail(self, message: str) -> None:
        line = self.text.count("\n", 0, self.pos) + 1
        raise ValueError(f"{message} at line {line}")

    def skip(self) -> None:
        """Advance past whitespace and comments."""
        text = self.text
        while self.pos < len(text):
            if text[self.pos].isspace():
                self.pos += 1
            elif text.startswith("//", self.pos):
                end = text.find("\n", self.pos)
                self.pos = len(text) if end < 0 else end
            elif text.startswith("/*", self.pos):
                end = text.find("*/", self.pos + 2)
                if end < 0:
                    self.fail("unterminated comment")
                self.pos = end + 2
            else:
                return

    def peek(self) -> str:
        self.skip()
        if self.pos >= len(self.text):
            self.fail("unexpected end of input")
        return self.text[self.pos]

    def value(self) -> Any:
        char = self.peek()
        if char == "{":
            return self.object()
        if char == "[":
            return self.array()
        if char in "\"'":
            return self.string()
        number = _NUMBER.match(self.text, self.pos)
        if number:
            self.pos = number.end()
            raw = number.group()
            if raw.lstrip("+-").lower().startswith("0x"):
                return int(raw, 16)
            return float(raw) if any(c in raw for c in ".eE") else int(raw)
        word = _IDENTIFIER.match(self.text, self.pos)
        if word and word.group() in _LITERALS:
            self.pos = word.end()
            return _LITERALS[word.group()]
        self.fail("unexpected token")
        return None

    def object(self) -> dict[str, Any]:
        self.pos += 1
        out: dict[str, Any] = {}
        while True:
            char = self.peek()
            if char == "}":
                self.pos += 1
                return out
            if char in "\"'":
                key = self.string()
            else:
                word = _IDENTIFIER.match(self.text, self.pos)
                if not word:
                    self.fail("expected a key")
                    raise AssertionError
                key = word.group()
                self.pos = word.end()
            if self.peek() != ":":
                self.fail("expected ':'")
            self.pos += 1
            out[key] = self.value()
            if not self.separator("}"):
                return out

    def array(self) -> list[Any]:
        self.pos += 1
        out: list[Any] = []
        while True:
            if self.peek() == "]":
                self.pos += 1
                return out
            out.append(self.value())
            if not self.separator("]"):
                return out

    def separator(self, closer: str) -> bool:
        """Consume ``,`` (more items may follow) or the closer (container done)."""
        char = self.peek()
        self.pos += 1
        if char == ",":
            return True
        if char != closer:
            self.pos -= 1
            self.fail(f"expected ',' or '{closer}'")
        return False

    def string(self) -> str:
        quote = self.text[self.pos]
        self.pos += 1
        out: list[str] = []
        text = self.text
        while self.pos < len(text):
            char = text[self.pos]
            self.pos += 1
            if char == quote:
                return "".join(out)
            if char != "\\":
                out.append(char)
                continue
            if self.pos >= len(text):
                break
            escaped = text[self.pos]
            self.pos += 1
            if escaped == "u":
                code = text[self.pos : self.pos + 4]
                if not re.fullmatch(r"[0-9a-fA-F]{4}", code):
                    self.fail("bad unicode escape")
                out.append(chr(int(code, 16)))
                self.pos += 4
            elif escaped == "\n":
                continue
            else:
                out.append(_ESCAPES.get(escaped, escaped))
        self.fail("unterminated string")
        return ""
