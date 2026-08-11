"""Auth and bootstrap helpers for HTTP integration tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from octop.infra.setup.password_file import WIZARD_FILE_NAME, read_password

# Meets ``validate_password_policy`` (letter + digit, length ≥ 8).
TEST_PASSWORD = "TestPass12"


def _wizard_password_home(home: Path) -> Path:
    """Resolve wizard password dir: file lives at ``~/octop-login.txt``, not under ``~/.octop/``."""
    for cand in (home, home.parent, Path.home()):
        if (cand / WIZARD_FILE_NAME).exists():
            return cand
    return home


async def wizard_token(client: httpx.AsyncClient, home: Path) -> str:
    pw = read_password(_wizard_password_home(home))
    assert pw is not None
    r = await client.post("/api/setup/verify-password", json={"password": pw})
    r.raise_for_status()
    return r.json()["wizard_token"]


async def bootstrap_admin(
    client: httpx.AsyncClient,
    home: Path,
    *,
    username: str = "admin",
    password: str = TEST_PASSWORD,
) -> httpx.Response:
    """Run verify-password → initial-admin → finish (creates default ``main`` agent)."""
    pw = read_password(_wizard_password_home(home))
    assert pw is not None, "wizard password file missing"
    tok_resp = await client.post("/api/setup/verify-password", json={"password": pw})
    tok = tok_resp.json()["wizard_token"]
    r = await client.post(
        "/api/setup/initial-admin",
        json={"username": username, "password": password},
        headers={"Authorization": f"Bearer {tok}"},
    )
    r.raise_for_status()
    finish = await client.post(
        "/api/setup/finish",
        json={"provider_draft": None},
        headers={"Authorization": f"Bearer {tok}"},
    )
    finish.raise_for_status()
    return r


async def login(
    client: httpx.AsyncClient,
    *,
    username: str = "admin",
    password: str = TEST_PASSWORD,
) -> str:
    r = await client.post("/api/auth/login", json={"username": username, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def auth_header(
    client: httpx.AsyncClient,
    *,
    username: str = "admin",
    password: str = TEST_PASSWORD,
) -> dict[str, str]:
    return bearer(await login(client, username=username, password=password))


async def seed_openai_provider(
    client: httpx.AsyncClient,
    auth: dict[str, str],
    *,
    name: str = "openai",
    api_key: str = "k",
) -> None:
    r = await client.post(
        "/api/admin/providers",
        headers=auth,
        json={
            "name": name,
            "kind": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key": api_key,
            "models": [
                {
                    "id": "gpt-4o",
                    "name": "GPT-4o",
                    "enabled": True,
                    "input": ["text"],
                    "thinking": False,
                }
            ],
        },
    )
    r.raise_for_status()


async def create_agent(
    client: httpx.AsyncClient,
    auth: dict[str, str],
    *,
    name: str = "bot",
    config: dict[str, Any] | None = None,
) -> str:
    body = {
        "name": name,
        "config": config or {"providers": ["openai"], "default_model": "openai:gpt-4o"},
    }
    r = await client.post("/api/agents", headers=auth, json=body)
    r.raise_for_status()
    data = r.json()
    return data.get("agent_id") or data["id"]


async def create_user(
    client: httpx.AsyncClient,
    admin_auth: dict[str, str],
    *,
    username: str,
    password: str = TEST_PASSWORD,
    role: str = "user",
) -> dict[str, str]:
    r = await client.post(
        "/api/users",
        headers=admin_auth,
        json={"username": username, "password": password, "role": role},
    )
    r.raise_for_status()
    return await auth_header(client, username=username, password=password)


async def ensure_users(
    client: httpx.AsyncClient,
    admin_auth: dict[str, str],
    *usernames: str,
    password: str = TEST_PASSWORD,
) -> dict[str, dict[str, str]]:
    auths: dict[str, dict[str, str]] = {}
    for username in usernames:
        auths[username] = await create_user(
            client,
            admin_auth,
            username=username,
            password=password,
        )
    return auths


async def resolve_user_id(
    client: httpx.AsyncClient,
    admin_auth: dict[str, str],
    username: str,
) -> int:
    users = (await client.get("/api/users", headers=admin_auth)).json()
    return next(u["id"] for u in users if u["username"] == username)


async def create_provider(
    client: httpx.AsyncClient,
    auth: dict[str, str],
    *,
    name: str = "openai",
    kind: str = "openai",
    api_key: str = "k",
    **extra: Any,
) -> dict[str, Any]:
    body: dict[str, Any] = {"name": name, "kind": kind, "api_key": api_key, **extra}
    r = await client.post("/api/admin/providers", headers=auth, json=body)
    r.raise_for_status()
    return r.json()
