"""The Codex OAuth token file must never be left half written."""

from __future__ import annotations

import json
import os

import pytest

from octop.infra.agents.providers import codex_oauth


class _Paths:
    def __init__(self, root):
        self._root = root


def test_a_failed_save_keeps_the_previous_token(tmp_path, monkeypatch):
    token_file = tmp_path / "codex_oauth.json"
    monkeypatch.setattr(codex_oauth, "oauth_token_file", lambda paths: token_file)
    before = {"access": "old", "refresh": "old", "expires": 1}
    token_file.write_text(json.dumps(before), encoding="utf-8")

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", _boom)

    with pytest.raises(OSError):
        codex_oauth.save_codex_token(
            _Paths(tmp_path),
            codex_oauth.CodexOAuthCredentials(
                access="new", refresh="new", expires=2, account_id=""
            ),
        )

    # A truncating write would leave JSON that load_codex_token cannot parse, and
    # the file stays on disk, so the user would just be logged out.
    assert json.loads(token_file.read_text(encoding="utf-8")) == before
    assert list(tmp_path.glob("*.tmp")) == []


def test_the_token_is_saved_with_owner_only_permissions(tmp_path, monkeypatch):
    token_file = tmp_path / "codex_oauth.json"
    monkeypatch.setattr(codex_oauth, "oauth_token_file", lambda paths: token_file)

    codex_oauth.save_codex_token(
        _Paths(tmp_path),
        codex_oauth.CodexOAuthCredentials(access="a", refresh="r", expires=3, account_id="x"),
    )

    payload = json.loads(token_file.read_text(encoding="utf-8"))
    assert payload["access"] == "a"
    assert os.stat(token_file).st_mode & 0o777 == 0o600
