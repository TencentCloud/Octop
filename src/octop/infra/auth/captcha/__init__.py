"""Login captcha: provider registry, config, and verify orchestration."""

from __future__ import annotations

from octop.infra.auth.captcha.config import (
    CaptchaEnv,
    current_env,
    install_env,
    snapshot_env,
    validate_boot,
)
from octop.infra.auth.captcha.providers import (
    CaptchaProvider,
    get_provider,
    list_providers,
    parse_slug,
    register,
)
from octop.infra.auth.captcha.store import (
    SETTINGS_KEY,
    has_readable_blob,
    load_effective,
    load_view,
    public_config,
    save_settings,
)
from octop.infra.auth.captcha.verify import ensure_captcha, set_test_siteverify_url
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.settings import SettingsRepo

__all__ = [
    "CaptchaEnv",
    "CaptchaProvider",
    "SETTINGS_KEY",
    "boot_from_services",
    "current_env",
    "ensure_captcha",
    "get_provider",
    "has_readable_blob",
    "install_env",
    "list_providers",
    "load_effective",
    "load_view",
    "parse_slug",
    "public_config",
    "register",
    "save_settings",
    "set_test_siteverify_url",
    "snapshot_env",
    "validate_boot",
]


def boot_from_services(settings_repo: SettingsRepo, secret_repo: SecretRepo) -> None:
    env = snapshot_env()
    install_env(env)
    validate_boot(env, has_readable_blob=has_readable_blob(settings_repo, secret_repo))
