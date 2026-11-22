#!/usr/bin/env python3
"""Migrate legacy Octop memory-MCP tokens into octop-memory (internal).

Copies the sha256 digest, so existing clients keep the **same plaintext** after
the switch; only their MCP URL changes. Each token is bound to its expert's
default memory space; multi-expert / unrestricted tokens keep access through
space grants.

Typical internal run (same host or reachable memory service):

    export OCTOP_HOME=/data/octop
    octop-memory auth code --all            # on the memory host
    PYTHONPATH=src python scripts/migrate_memory_tokens.py \
        --memory-url http://127.0.0.1:8790 --code mcode_... --dry-run

Drop ``--dry-run`` to apply. Re-running is safe: already-migrated hashes are
reported as skipped.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from octop.config import load_config  # noqa: E402
from octop.infra.agents.memory_default_space import default_space_for  # noqa: E402


def _post(url: str, payload: dict[str, Any], token: str | None = None) -> dict[str, Any]:
    headers = {"content-type": "application/json", "accept": "application/json"}
    if token:
        headers["authorization"] = f"Bearer {token}"
    req = request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode() or "{}")
    except error.HTTPError as exc:
        detail = exc.read().decode()
        if exc.code == 409:
            return {"_conflict": True}
        raise RuntimeError(f"{url} -> {exc.code}: {detail}") from exc


def _exchange(memory_url: str, code: str) -> str:
    payload = _post(f"{memory_url}/api/admin/session/exchange", {"code": code})
    token = payload.get("session_token")
    if not token:
        raise RuntimeError("no session_token in exchange response")
    return str(token)


def _spaces_for(
    expert_ids: list[str] | None,
    user_id: int,
    agents: list[sqlite3.Row],
    octop_config: Any,
    octop_home: Path,
) -> list[dict[str, Any]]:
    selected = expert_ids or [row["agent_id"] for row in agents if row["user_id"] == user_id]
    out: list[dict[str, Any]] = []
    for agent_id in selected:
        row = next((item for item in agents if item["agent_id"] == agent_id), None)
        if row is None:
            continue
        cfg = json.loads(row["config_json"] or "{}") or {}
        workspace = Path(cfg.get("workspace_dir") or octop_home / "agents" / agent_id)
        space = default_space_for(
            agent_id=agent_id, cfg=cfg, octop_config=octop_config, workspace_dir=workspace
        )
        if not space.usable:
            raise RuntimeError(f"expert {agent_id}: {space.reason}")
        out.append(
            {
                "agent_id": agent_id,
                "space_id": space.space_id,
                "backend": space.backend,
                "backend_config": space.backend_config,
            }
        )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--memory-url", default="http://127.0.0.1:8790")
    parser.add_argument("--code", required=True, help="octop-memory auth code --all")
    parser.add_argument("--octop-home", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    memory_url = args.memory_url.rstrip("/")
    octop_home = Path(args.octop_home or __import__("os").environ.get("OCTOP_HOME") or "~/.octop").expanduser()
    db_path = octop_home / "octop.db"
    config_path = octop_home / "config.json"
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    agents = connection.execute("SELECT agent_id, user_id, config_json FROM agents").fetchall()
    tokens = connection.execute("SELECT * FROM memory_mcp_tokens").fetchall()
    connection.close()
    octop_config = load_config(config_path)

    session = _exchange(memory_url, args.code)
    report: dict[str, Any] = {"migrated": [], "skipped": [], "failed": []}

    for row in tokens:
        try:
            expert_ids = json.loads(row["expert_ids"]) if row["expert_ids"] else None
            spaces = _spaces_for(expert_ids, int(row["user_id"]), agents, octop_config, octop_home)
            if not spaces:
                report["skipped"].append({"token": row["name"], "reason": "no expert"})
                continue
            primary = spaces[0]
            extra = spaces[1:]
            if args.dry_run:
                report["migrated"].append(
                    {
                        "name": row["name"],
                        "primary_space": primary["space_id"],
                        "grants": [item["space_id"] for item in extra],
                    }
                )
                continue
            # Idempotent: creating an existing space returns 409 from the admin API.
            _post(
                f"{memory_url}/api/admin/spaces",
                {
                    "space_id": primary["space_id"],
                    "display_name": f"{primary['agent_id']} 的记忆",
                    "backend": primary["backend"],
                    "backend_config": primary["backend_config"],
                },
                session,
            )
            for item in extra:
                _post(
                    f"{memory_url}/api/admin/spaces",
                    {
                        "space_id": item["space_id"],
                        "display_name": f"{item['agent_id']} 的记忆",
                        "backend": item["backend"],
                        "backend_config": item["backend_config"],
                    },
                    session,
                )
            result = _post(
                f"{memory_url}/api/admin/spaces/{primary['space_id']}/tokens/import",
                {
                    "token_hash": row["token_hash"],
                    "token_hint": row["token_hint"],
                    "client_name": row["name"],
                    "scopes": ["read", "write", "review"],
                    "disabled_clients": json.loads(row["disabled_clients"] or "[]"),
                    "client_stats": json.loads(row["client_stats"] or "{}"),
                    "created_at": row["created_at"],
                    "last_used_at": row["last_used_at"],
                    "revoked_at": row["revoked_at"],
                    "octop_token_id": row["token_id"],
                    "extra_space_ids": [item["space_id"] for item in extra],
                },
                session,
            )
            if result.get("_conflict"):
                report["skipped"].append({"name": row["name"], "reason": "already migrated"})
            else:
                report["migrated"].append(
                    {
                        "name": row["name"],
                        "space": primary["space_id"],
                        "grants": [item["space_id"] for item in extra],
                    }
                )
        except Exception as exc:  # noqa: BLE001 - report per token, keep going
            report["failed"].append({"name": row["name"], "error": str(exc)})

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not report["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
