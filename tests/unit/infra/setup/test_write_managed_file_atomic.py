"""A managed file (systemd unit) must never be left half written."""

from __future__ import annotations

import os

import pytest

from octop.infra.setup import service


def test_a_failed_publish_keeps_the_previous_unit(tmp_path, monkeypatch):
    destination = tmp_path / "octop.service"
    destination.write_text("[Unit]\nDescription=old\n", encoding="utf-8")
    monkeypatch.setattr(service, "_needs_sudo", lambda path: False)

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", _boom)

    with pytest.raises(OSError):
        service._write_managed_file(destination, "[Unit]\nDescription=new\n", run_as_user="root")

    # A truncating write would leave a unit file systemd cannot parse, and the
    # service would stay down until the next successful install.
    assert destination.read_text(encoding="utf-8") == "[Unit]\nDescription=old\n"
    assert list(tmp_path.glob("*.tmp")) == []


def test_the_unit_is_written_with_the_expected_permissions(tmp_path, monkeypatch):
    destination = tmp_path / "octop.service"
    monkeypatch.setattr(service, "_needs_sudo", lambda path: False)

    service._write_managed_file(destination, "[Unit]\nDescription=new\n", run_as_user="root")

    assert destination.read_text(encoding="utf-8") == "[Unit]\nDescription=new\n"
    assert os.stat(destination).st_mode & 0o777 == 0o644
