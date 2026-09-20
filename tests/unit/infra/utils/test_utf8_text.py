"""Tests for UTF-8 coercion of third-party package text files."""

from __future__ import annotations

import pytest

from octop.infra.utils.utf8_text import (
    InvalidSkillManifestEncodingError,
    coerce_utf8_text_bytes,
    looks_like_text_path,
    repair_known_utf8_corruption,
    require_utf8_skill_manifest,
)


def test_looks_like_text_path() -> None:
    assert looks_like_text_path("SKILL.md")
    assert looks_like_text_path("references/guide.yaml")
    assert not looks_like_text_path("assets/icon.png")


def test_coerce_repairs_skillhub_le_corruption() -> None:
    # Upstream ecommerce-copy-humanizer-zh shipped ``≤`` as ``e2 6a 24``.
    raw = "每句 ".encode() + b"\xe2j$" + "15 字".encode()
    fixed = coerce_utf8_text_bytes(raw, path="notes.md")
    assert fixed.decode("utf-8") == "每句 ≤15 字"


def test_coerce_leaves_valid_utf8_unchanged() -> None:
    raw = "hello ≤ world".encode()
    assert coerce_utf8_text_bytes(raw, path="SKILL.md") == raw


def test_coerce_skips_binary_paths() -> None:
    raw = b"\xe2j$binary"
    assert coerce_utf8_text_bytes(raw, path="icon.png") == raw


def test_coerce_replaces_unknown_invalid_sequences_for_aux_text() -> None:
    raw = b"ok\xffstill"
    fixed = coerce_utf8_text_bytes(raw, path="notes.txt")
    assert fixed.decode("utf-8") == "ok\ufffdstill"


def test_repair_known_returns_none_for_unknown_corruption() -> None:
    assert repair_known_utf8_corruption(b"ok\xffstill") is None


def test_require_utf8_skill_manifest_repairs_known_corruption() -> None:
    raw = "每句 ".encode() + b"\xe2j$" + "15 字".encode()
    assert require_utf8_skill_manifest(raw).decode("utf-8") == "每句 ≤15 字"


def test_require_utf8_skill_manifest_rejects_unknown_corruption() -> None:
    with pytest.raises(InvalidSkillManifestEncodingError):
        require_utf8_skill_manifest(b"---\nname: bad\n---\n\xff\xfe")


def test_coerce_skill_manifest_rejects_unknown_corruption() -> None:
    with pytest.raises(InvalidSkillManifestEncodingError):
        coerce_utf8_text_bytes(b"---\nname: bad\n---\n\xff\xfe", path="SKILL.md")
