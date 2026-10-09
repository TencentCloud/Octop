"""Backup roundtrips model moving data with the deployment's separate key."""

from pathlib import Path

import pytest
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def deployment_key(_isolated_user_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Source/target homes in the existing roundtrip tests share an explicitly
    # provisioned deployment key. Missing/wrong keys have separate regression tests.
    monkeypatch.setenv("OCTOP_SECRET_KEY", Fernet.generate_key().decode())
