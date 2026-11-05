"""Mirror between the Workbench cloud credential and tccli's credential file."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from octop.infra.cloud.tencent import (
    CloudCredential,
    CloudError,
    credential_from_tccli,
    mirror_to_tccli,
    tccli_profile_for_user,
)


def _credential() -> CloudCredential:
    return CloudCredential(
        secret_id="AKIDtest000000000000",
        secret_key="secret-key-value",
        token="sts-token",
        expires_at=1793076962.0,
        access_token="access-token-value",
        access_expires_at=1793076958.0,
        refresh_token="refresh-token-value",
        open_id="open-id-value",
        site="cn",
    )


@pytest.fixture()
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / ".tccli").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    # Windows Path.home() reads USERPROFILE, and a class-level patch keeps the
    # mirror off the runner's real profile even if the env lookup differs.
    monkeypatch.setattr(
        "octop.infra.cloud.tencent.Path.home",
        lambda: tmp_path,
    )
    monkeypatch.delenv("OCTOP_TCCLI_PROFILE_ISOLATION", raising=False)
    return tmp_path


def test_mirror_writes_credential_and_pointer(home: Path) -> None:
    assert mirror_to_tccli(_credential(), uid=1) == "ok"

    path = home / ".tccli" / "default.credential"
    payload = json.loads(path.read_text())
    assert payload["type"] == "oauth"
    assert payload["secretId"] == "AKIDtest000000000000"
    assert payload["expiresAt"] == 1793076962.0
    assert payload["oauth"]["refreshToken"] == "refresh-token-value"
    assert payload["oauth"]["openId"] == "open-id-value"

    # 600: the file carries STS + refresh token. Windows only honors the
    # read-only flag, so the Unix mode is meaningful on POSIX.
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    # 指针文件告诉技能脚本该读哪个 profile
    pointer = home / ".tccli" / ".octop-profile"
    assert pointer.read_text().strip() == "default"
    if os.name == "posix":
        assert stat.S_IMODE(pointer.stat().st_mode) == 0o600


def test_mirror_skips_without_tccli_dir(home: Path) -> None:
    for child in (home / ".tccli").iterdir():
        child.unlink()
    (home / ".tccli").rmdir()

    assert mirror_to_tccli(_credential(), uid=1) == "skipped"
    assert not (home / ".tccli").exists()


def test_mirror_reports_failure(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("octop.infra.cloud.tencent._write_private", boom)
    assert mirror_to_tccli(_credential(), uid=1) == "failed"
    assert not (home / ".tccli" / "default.credential").exists()


def test_credential_from_tccli_roundtrip(home: Path) -> None:
    original = _credential()
    assert mirror_to_tccli(original, uid=1) == "ok"

    parsed = credential_from_tccli(home / ".tccli" / "default.credential")
    assert parsed == original


def test_credential_from_tccli_rejects_static_key_file(home: Path) -> None:
    path = home / ".tccli" / "default.credential"
    path.write_text(json.dumps({"type": "ak", "secretId": "a", "secretKey": "b"}))

    with pytest.raises(CloudError):
        credential_from_tccli(path)


def test_profile_isolation_is_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OCTOP_TCCLI_PROFILE_ISOLATION", raising=False)
    assert tccli_profile_for_user(7) == "default"

    monkeypatch.setenv("OCTOP_TCCLI_PROFILE_ISOLATION", "1")
    assert tccli_profile_for_user(7) == "octop-7"

    # 无用户上下文（CLI 直接调用）时不能用隔离名
    assert tccli_profile_for_user(None) == "default"


def test_isolated_profile_writes_separate_file(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTOP_TCCLI_PROFILE_ISOLATION", "1")
    assert mirror_to_tccli(_credential(), uid=3) == "ok"

    assert (home / ".tccli" / "octop-3.credential").is_file()
    assert not (home / ".tccli" / "default.credential").exists()
    assert (home / ".tccli" / ".octop-profile").read_text().strip() == "octop-3"
