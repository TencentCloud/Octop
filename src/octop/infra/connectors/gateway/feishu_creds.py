"""Materialize lark-cli config for headless Octop connector instances."""

from __future__ import annotations

import hashlib
import os
from contextlib import suppress
from pathlib import Path

from octop.infra.connectors.gateway.cli_runner import resolve_binary, run_cli

_FINGERPRINT_NAME = ".octop_feishu_fingerprint"
_BRAND = "feishu"


def prepare_feishu_cli_env(
    config_dir: Path,
    *,
    app_id: str,
    app_secret: str,
    default_as: str = "bot",
) -> tuple[str, dict[str, str]]:
    """Resolve binary, scrub external app env, set CONFIG_DIR, ensure config."""
    app_id = str(app_id or "").strip()
    app_secret = str(app_secret or "").strip()
    if not app_id or not app_secret:
        raise ValueError("Feishu app_id and app_secret are required")
    binary = resolve_binary("lark-cli")
    env = os.environ.copy()
    # External env credentials break bot token resolution — only use CONFIG_DIR.
    env.pop("LARKSUITE_CLI_APP_ID", None)
    env.pop("LARKSUITE_CLI_APP_SECRET", None)
    env["LARKSUITE_CLI_CONFIG_DIR"] = str(config_dir)
    ensure_feishu_cli_config(
        config_dir,
        binary=binary,
        app_id=app_id,
        app_secret=app_secret,
        env=env,
        default_as=default_as,
    )
    return binary, env


def ensure_feishu_cli_config(
    config_dir: Path,
    *,
    binary: str,
    app_id: str,
    app_secret: str,
    env: dict[str, str],
    default_as: str = "bot",
) -> None:
    """Write/refresh lark-cli config via ``config init``.

    Do **not** set ``LARKSUITE_CLI_APP_ID`` / ``LARKSUITE_CLI_APP_SECRET`` in the
    process environment: those put lark-cli into "external credentials" mode where
    ``auth status`` and bot token resolution fail.

    ``default_as`` is ``bot`` or ``user`` (persisted preference after device login).
    """
    config_dir.mkdir(parents=True, exist_ok=True)
    identity = _normalize_default_as(default_as)
    fingerprint = hashlib.sha256(f"{app_id}\0{app_secret}".encode()).hexdigest()
    marker = config_dir / _FINGERPRINT_NAME
    config_path = config_dir / "config.json"
    if (
        marker.is_file()
        and config_path.is_file()
        and marker.read_text(encoding="utf-8").strip() == fingerprint
    ):
        _ensure_default_as(binary, env, identity)
        return

    # config init reads App Secret from stdin (--app-secret-stdin).
    run_cli(
        [
            binary,
            "config",
            "init",
            "--app-id",
            app_id,
            "--app-secret-stdin",
            "--brand",
            _BRAND,
        ],
        env=env,
        timeout_s=60.0,
        stdin_text=app_secret,
    )
    _ensure_default_as(binary, env, identity)
    marker.write_text(fingerprint + "\n", encoding="utf-8")
    marker.chmod(0o600)


def _normalize_default_as(value: str) -> str:
    raw = str(value or "bot").strip().lower()
    return "user" if raw == "user" else "bot"


def _ensure_default_as(binary: str, env: dict[str, str], identity: str) -> None:
    # Older CLI / already set — non-fatal if auth status still works.
    with suppress(ValueError):
        run_cli([binary, "config", "default-as", identity], env=env, timeout_s=30.0)
