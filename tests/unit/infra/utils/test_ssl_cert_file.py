"""Unit tests for the SSL_CERT_FILE defaulting helper."""

from __future__ import annotations

import os
import sys

import certifi
import pytest

from octop.infra.utils.ssl_cert_file import ensure_ssl_cert_file


def test_sets_cert_file_on_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    ensure_ssl_cert_file()
    assert os.environ["SSL_CERT_FILE"] == certifi.where()


def test_sets_cert_file_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("platform.system", lambda: "Windows")
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    ensure_ssl_cert_file()
    assert os.environ["SSL_CERT_FILE"] == certifi.where()


def test_preserves_user_provided_cert_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setenv("SSL_CERT_FILE", "/custom/ca.pem")
    ensure_ssl_cert_file()
    assert os.environ["SSL_CERT_FILE"] == "/custom/ca.pem"


def test_noop_on_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    ensure_ssl_cert_file()
    assert "SSL_CERT_FILE" not in os.environ


def test_noop_without_certifi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.setitem(sys.modules, "certifi", None)
    ensure_ssl_cert_file()
    assert "SSL_CERT_FILE" not in os.environ
