"""The ACME account key must never be left half written."""

from __future__ import annotations

import os

import pytest

from octop.infra.setup.tls import acme_issue


def test_a_failed_publish_leaves_no_key_behind(tmp_path, monkeypatch):
    path = tmp_path / "account.key"

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", _boom)

    with pytest.raises(OSError):
        acme_issue._load_or_create_account_key(path)

    # A truncating write would leave a partial key here, and the loader only
    # generates one when the path is absent, so every later ACME run would fail
    # on it until someone deleted the file by hand.
    assert not path.exists()


def test_the_key_is_created_with_owner_only_permissions(tmp_path):
    path = tmp_path / "account.key"

    key = acme_issue._load_or_create_account_key(path)

    assert path.is_file()
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert key.key is not None


def test_an_existing_key_is_reused(tmp_path):
    path = tmp_path / "account.key"
    first = acme_issue._load_or_create_account_key(path)

    second = acme_issue._load_or_create_account_key(path)

    assert second.key.private_numbers() == first.key.private_numbers()
