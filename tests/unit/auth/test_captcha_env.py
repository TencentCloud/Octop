"""Boot-time CaptchaEnv snapshot."""

from __future__ import annotations

import pytest

from octop.infra.auth.captcha import config as captcha_config
from octop.infra.auth.captcha import current_env, install_env, snapshot_env, validate_boot


@pytest.fixture(autouse=True)
def _reset_installed_env() -> None:
    captcha_config._INSTALLED = None
    yield
    captcha_config._INSTALLED = None


def test_empty_env_snapshots_as_slider() -> None:
    env = snapshot_env({})
    assert env.provider == "slider"
    assert env.site_key == ""
    assert env.secret == ""
    assert env.v3_min_score == 0.5


def test_slider_env_is_complete() -> None:
    env = snapshot_env({"OCTOP_CAPTCHA_PROVIDER": "slider"})
    assert env.provider == "slider"
    validate_boot(env, has_readable_blob=False)


def test_strong_env_without_keys_refuses_boot_when_no_blob() -> None:
    env = snapshot_env({"OCTOP_CAPTCHA_PROVIDER": "turnstile"})
    with pytest.raises(ValueError, match="OCTOP_CAPTCHA_SITE_KEY"):
        validate_boot(env, has_readable_blob=False)


def test_tencent_env_without_cam_keys_refuses_boot_when_no_blob() -> None:
    env = snapshot_env(
        {
            "OCTOP_CAPTCHA_PROVIDER": "tencent",
            "OCTOP_CAPTCHA_SITE_KEY": "195642000",
            "OCTOP_CAPTCHA_SECRET": "app-secret",
        }
    )
    with pytest.raises(ValueError, match="OCTOP_CAPTCHA_CAM_SECRET_ID"):
        validate_boot(env, has_readable_blob=False)


def test_strong_env_without_keys_is_ok_when_blob_exists() -> None:
    env = snapshot_env({"OCTOP_CAPTCHA_PROVIDER": "turnstile"})
    validate_boot(env, has_readable_blob=True)


def test_installed_snapshot_ignores_later_os_environ_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OCTOP_CAPTCHA_PROVIDER", "slider")
    install_env(snapshot_env())
    monkeypatch.setenv("OCTOP_CAPTCHA_PROVIDER", "turnstile")
    monkeypatch.setenv("OCTOP_CAPTCHA_SITE_KEY", "0xsite")
    monkeypatch.setenv("OCTOP_CAPTCHA_SECRET", "0xsecret")
    assert current_env().provider == "slider"
