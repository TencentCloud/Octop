"""tests/integration/test_git_api.py — workspace git endpoints.

Uses the standard agent fixture; the workspace is turned into a git repo
on the fly so status/diff/log/staging can be exercised over HTTP.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


@pytest.fixture
async def git_env(env_with_agent):
    client, srv, auth, agent_id = env_with_agent
    ws_dir = srv.app_runtime.agent_registry.resolve_workspace_dir(agent_id)
    _git(ws_dir, "init", "-b", "main")
    _git(ws_dir, "config", "user.email", "test@example.com")
    _git(ws_dir, "config", "user.name", "Test")
    (ws_dir / "note.md").write_text("hello\n")
    _git(ws_dir, "add", "note.md")
    _git(ws_dir, "commit", "-m", "init")
    yield client, srv, auth, agent_id, ws_dir


async def test_unknown_agent_404(git_env: Any) -> None:
    client, _srv, auth, _agent_id, _ws = git_env
    r = await client.get("/api/agents/no-such-agent/git/status", headers=auth)
    assert r.status_code == 404


async def test_status_roundtrip(git_env: Any) -> None:
    client, _srv, auth, agent_id, ws_dir = git_env
    (ws_dir / "note.md").write_text("hello\nworld\n")
    (ws_dir / "extra.txt").write_text("new\n")

    r = await client.get(f"/api/agents/{agent_id}/git/status", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_repo"] is True
    assert body["git_available"] is True
    assert body["branch"] == "main"
    rows = {(f["status"], f["staged"], f["path"]): f for f in body["files"]}
    modified = rows[("modified", False, "note.md")]
    assert modified["added"] == 1
    assert rows[("untracked", False, "extra.txt")]["added"] == 1
    assert body["added"] == 2


async def test_status_without_git_directory_reports_not_repo(env_with_agent) -> None:
    client, _srv, auth, agent_id = env_with_agent
    r = await client.get(f"/api/agents/{agent_id}/git/status", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_repo"] is False
    assert body["files"] == []


async def test_diff_and_log(git_env: Any) -> None:
    client, _srv, auth, agent_id, ws_dir = git_env
    (ws_dir / "note.md").write_text("hello\nchanged\n")

    r = await client.get(
        f"/api/agents/{agent_id}/git/diff",
        params={"path": "note.md", "staged": "false"},
        headers=auth,
    )
    assert r.status_code == 200, r.text
    assert "+changed" in r.json()["diff"]

    r = await client.get(f"/api/agents/{agent_id}/git/log", params={"limit": 5}, headers=auth)
    assert r.status_code == 200, r.text
    commits = r.json()
    assert len(commits) == 1
    assert commits[0]["subject"] == "init"


async def test_stage_commit_and_write_guards(git_env: Any) -> None:
    client, _srv, auth, agent_id, ws_dir = git_env
    (ws_dir / "feature.txt").write_text("work\n")

    r = await client.post(
        f"/api/agents/{agent_id}/git/stage",
        headers=auth,
        json={"paths": ["feature.txt"]},
    )
    assert r.status_code == 200, r.text

    r = await client.post(
        f"/api/agents/{agent_id}/git/commit",
        headers=auth,
        json={"message": "feat: add feature"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["commit"]

    r = await client.post(
        f"/api/agents/{agent_id}/git/commit",
        headers=auth,
        json={"message": "nothing staged"},
    )
    assert r.status_code == 400, r.text

    r = await client.post(
        f"/api/agents/{agent_id}/git/discard",
        headers=auth,
        json={"paths": ["../escape.txt"]},
    )
    assert r.status_code == 400, r.text


async def test_git_requires_owner(env_alice_bob_agent) -> None:
    client, _admin_auth, alice_auth, bob_auth, agent_id = env_alice_bob_agent
    r = await client.get(f"/api/agents/{agent_id}/git/status", headers=bob_auth)
    assert r.status_code == 403
    r = await client.get(f"/api/agents/{agent_id}/git/status", headers=alice_auth)
    assert r.status_code == 200
