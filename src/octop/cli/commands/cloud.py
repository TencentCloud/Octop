"""``octop cloud`` — bridge the Workbench cloud login and the local tccli file.

Why this exists
---------------
The Workbench keeps a per-user Tencent Cloud login (local files on SQLite,
the shared ``secrets`` table on PostgreSQL) while the ops expert's skill
drives ``tccli``
off ``~/.tccli/<profile>.credential``. Authorizing in one place used to leave
the other side stale — the user saw "I just authorized, why is it expired
again?". ``import-tccli`` closes the loop in the tccli → Octop direction
(the reverse direction is mirrored automatically whenever the Workbench
authorizes or renews).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from octop.infra.errors import OctopError


@click.group()
def cloud() -> None:
    """Tencent Cloud credential helpers."""


def _first_admin_id() -> int | None:
    """First admin user id, so an unattended import (agent → Workbench) has an owner."""
    from octop.cli.support.db import open_cli_services

    try:
        with open_cli_services() as services:
            admins = [row for row in services.user_repo.list() if row.role == "admin"]
    except Exception:  # noqa: BLE001 - CLI fallback must not raise
        return None
    if not admins:
        return None
    return int(min(admins, key=lambda row: int(row.id)).id)


def _one_line(credential: Any) -> str:
    import time

    remaining = int(credential.expires_at - time.time())
    hours, minutes = max(0, remaining // 3600), max(0, (remaining % 3600) // 60)
    return f"有效 {hours}小时{minutes}分钟（STS 到期 {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(credential.expires_at))}）"


@cloud.command("import-tccli")
@click.option("--profile", default="default", show_default=True, help="tccli profile name.")
@click.option("--user", "as_user", default=None, help="Import for another user (admin only).")
@click.option(
    "--json", "as_json", is_flag=True, default=False, help="Print machine-readable status."
)
@click.option("--quiet", is_flag=True, default=False, help="Only print errors.")
def import_tccli(profile: str, as_user: str | None, as_json: bool, quiet: bool) -> None:
    """Import ``~/.tccli/<profile>.credential`` into the Octop cloud store.

    Run right after an interactive tccli/OAuth login so the Workbench console
    (and every other surface) shares the same credential, with no second scan.
    """
    import time

    from octop.cli.support.acting import resolve_cli_acting_user_id
    from octop.cli.support.db import open_cli_services
    from octop.infra.cloud.tencent import (
        CRED_REFRESH_SAFE_S,
        CloudError,
        credential_from_tccli,
        open_cloud_credential_store,
        refresh_credential,
    )
    from octop.infra.utils.paths import PathLayout

    path = Path.home() / ".tccli" / f"{profile}.credential"
    if not path.is_file():
        raise SystemExit(f"error: tccli 凭证不存在: {path}")

    try:
        credential = credential_from_tccli(path)
    except CloudError as exc:
        raise SystemExit(f"error: {exc}") from exc

    refreshed = False
    if credential.remaining() <= CRED_REFRESH_SAFE_S and credential.can_refresh():
        try:
            credential = refresh_credential(credential)
            refreshed = True
        except CloudError as exc:
            raise SystemExit(f"error: 本机凭证已失效: {exc}") from exc

    try:
        uid = resolve_cli_acting_user_id(None, as_user)
    except OctopError as exc:
        # Unattended call (skill script after an OAuth login): fall back to the
        # first admin instead of failing the sync.
        fallback = _first_admin_id() if as_user is None else None
        if fallback is None:
            raise SystemExit(f"error: {exc}") from exc
        uid = fallback

    paths = PathLayout.from_env()
    with open_cli_services() as services:
        store = open_cloud_credential_store(
            paths.root,
            services.config,
            services.repos.secret_repo,
        )
        store.save(uid, credential)

    payload = {
        "user_id": uid,
        "profile": profile,
        "refreshed": refreshed,
        "expires_at": credential.expires_at,
        "remaining_seconds": int(credential.expires_at - time.time()),
        "can_refresh": credential.can_refresh(),
    }
    if as_json:
        click.echo(json.dumps(payload, ensure_ascii=False))
    elif not quiet:
        click.echo(f"✅ 已导入 user={uid} profile={profile}，{_one_line(credential)}")
        if refreshed:
            click.echo("   （导入前已自动续期一次）")
