"""tests/integration/test_file_checkpoints_api.py — per-turn checkpoint endpoints.

Seeds checkpoint files under OCTOP_HOME and workspace files on disk, then
exercises summary / diff / rewind preview + apply over HTTP, including the
all-or-nothing rewind gate.
"""

from __future__ import annotations

from typing import Any

from octop.infra.agents.file_checkpoints import save_checkpoints
from octop.infra.utils.paths import PathLayout

MSG_ID = "01JTESTMSG0000000000000000"


def _seed_turn(agent_id: str, thread_id: str, changes: list[dict[str, Any]]) -> None:
    save_checkpoints(PathLayout.from_env().root, agent_id, thread_id, MSG_ID, changes)


async def test_summary_diff_and_rewind_roundtrip(env_with_agent) -> None:
    client, srv, auth, agent_id = env_with_agent
    ws_dir = srv.app_runtime.agent_registry.resolve_workspace_dir(agent_id)
    thread_id = "th-checkpoints"
    (ws_dir / "story.md").write_text("v2\n")
    (ws_dir / "created.md").write_text("fresh\n")
    _seed_turn(
        agent_id,
        thread_id,
        [
            {"path": "story.md", "before": "v1\n", "after": "v2\n"},
            {"path": "created.md", "before": None, "after": "fresh\n"},
        ],
    )
    base = f"/api/agents/{agent_id}/threads/{thread_id}/messages/{MSG_ID}/files"

    r = await client.get(f"{base}/summary", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reverted"] is False
    files = {f["path"]: f for f in body["files"]}
    assert files["story.md"]["added"] == 1 and files["story.md"]["removed"] == 1
    assert files["created.md"]["added"] == 1 and files["created.md"]["removed"] == 0
    assert body["additions"] == 2

    r = await client.get(f"{base}/diff", params={"path": "story.md"}, headers=auth)
    assert r.status_code == 200, r.text
    assert "+v2" in r.json()["diff"]

    r = await client.get(f"{base}/rewind/preview", headers=auth)
    assert r.status_code == 200, r.text
    preview = r.json()
    assert preview["can_apply"] is True
    assert {f["path"] for f in preview["safe"]} == {"story.md", "created.md"}

    r = await client.post(f"{base}/rewind/apply", headers=auth)
    assert r.status_code == 200, r.text
    assert sorted(r.json()["applied"]) == ["created.md", "story.md"]
    assert (ws_dir / "story.md").read_text() == "v1\n"
    assert not (ws_dir / "created.md").exists()

    r = await client.get(f"{base}/summary", headers=auth)
    assert r.json()["reverted"] is True


async def test_rewind_apply_blocked_when_any_file_unsafe(env_with_agent) -> None:
    client, srv, auth, agent_id = env_with_agent
    ws_dir = srv.app_runtime.agent_registry.resolve_workspace_dir(agent_id)
    thread_id = "th-blocked"
    (ws_dir / "story.md").write_text("v2\n")
    (ws_dir / "touched.md").write_text("after\n")
    _seed_turn(
        agent_id,
        thread_id,
        [
            {"path": "story.md", "before": "v1\n", "after": "v2\n"},
            {"path": "touched.md", "before": "before\n", "after": "after\n"},
        ],
    )
    # External modification after the turn: touched.md no longer matches.
    (ws_dir / "touched.md").write_text("externally changed\n")
    base = f"/api/agents/{agent_id}/threads/{thread_id}/messages/{MSG_ID}/files"

    r = await client.get(f"{base}/rewind/preview", headers=auth)
    preview = r.json()
    assert preview["can_apply"] is False
    assert [f["path"] for f in preview["unsafe"]] == ["touched.md"]

    r = await client.post(f"{base}/rewind/apply", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["applied"] == []
    assert body["blocked"] == ["touched.md"]
    # All-or-nothing: nothing was written.
    assert (ws_dir / "story.md").read_text() == "v2\n"


async def test_unknown_turn_reports_empty_summary(env_with_agent) -> None:
    client, _srv, auth, agent_id = env_with_agent
    base = f"/api/agents/{agent_id}/threads/th-none/messages/{MSG_ID}/files"
    r = await client.get(f"{base}/summary", headers=auth)
    assert r.status_code == 200, r.text
    assert r.json() == {"files": [], "additions": 0, "deletions": 0, "reverted": False}
    r = await client.get(f"{base}/diff", params={"path": "story.md"}, headers=auth)
    assert r.status_code == 404
