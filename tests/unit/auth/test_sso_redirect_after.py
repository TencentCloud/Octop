"""Tests for post-login redirect sanitization."""

from __future__ import annotations

import pytest

from octop.infra.auth.sso.redirect_after import sanitize_redirect_after


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (None, "/chat"),
        ("", "/chat"),
        ("/chat/thread-1", "/chat/thread-1"),
        ("/settings", "/settings"),
        ("https://attacker.example", "/chat"),
        ("//attacker.example", "/chat"),
        ("/\\attacker.example", "/chat"),
        ("/chat?next=https://attacker.example", "/chat"),
        ("chat", "/chat"),
    ],
)
def test_sanitize_redirect_after_keeps_only_safe_internal_paths(
    path: str | None, expected: str
) -> None:
    assert sanitize_redirect_after(path) == expected
