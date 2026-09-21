"""Team welcome uses member quick cards, not host-invented cards."""

from __future__ import annotations

import json
import tempfile
from types import SimpleNamespace

import pytest
from deepagents.backends.local_shell import LocalShellBackend
from harness_agent.backends.workspace import BackendWorkspace

from octop.infra.agents.teams.welcome import team_host_welcome_payload
from octop.infra.db.repos.agents import AgentRow


def _row(*, agent_id: str, kind: str = "expert", welcome: str | None = None) -> AgentRow:
    return AgentRow(
        id=1,
        agent_id=agent_id,
        user_id=1,
        name=agent_id,
        description=None,
        persona_mbti=None,
        default_model=None,
        system_prompt=None,
        enabled=1,
        config_json=None,
        last_state="running",
        last_error=None,
        created_at=0,
        updated_at=0,
        kind=kind,
        welcome_message=welcome,
    )


def _workspace(root: str) -> BackendWorkspace:
    backend = LocalShellBackend(root_dir=root, virtual_mode=False)
    return BackendWorkspace(backend, root)


def _prompt(title: str) -> dict[str, object]:
    return {
        "title": {"zh": title, "en": title},
        "description": {"zh": f"{title}说明", "en": f"{title} desc"},
        "prompt": {"zh": f"请{title}", "en": f"Please {title}"},
        "color": "#0d9488",
        "icon_name": "heart",
    }


async def _write_manifest(workspace: BackendWorkspace, payload: dict[str, object]) -> None:
    await workspace.awrite_text(
        ".octop/manifest.json",
        json.dumps(payload, ensure_ascii=False),
        force=True,
    )


@pytest.mark.asyncio
async def test_team_welcome_uses_member_cards_not_host_cards() -> None:
    with (
        tempfile.TemporaryDirectory() as host_dir,
        tempfile.TemporaryDirectory() as doc_dir,
        tempfile.TemporaryDirectory() as nurse_dir,
    ):
        host_ws = _workspace(host_dir)
        doc_ws = _workspace(doc_dir)
        nurse_ws = _workspace(nurse_dir)
        await _write_manifest(
            host_ws,
            {
                "welcome_message": {"zh": "团队介绍", "en": "Team intro"},
                "quick_prompts": [_prompt("主持卡")],
            },
        )
        await _write_manifest(
            doc_ws,
            {
                "welcome_message": {"zh": "我是医生", "en": "I am a doctor"},
                "quick_prompts": [_prompt("鉴别诊断"), _prompt("用药提醒")],
            },
        )
        await _write_manifest(
            nurse_ws,
            {
                "welcome_message": {"zh": "我是护士", "en": "I am a nurse"},
                "quick_prompts": [_prompt("健康打卡")],
            },
        )
        workspaces = {
            "host": host_ws,
            "doc": doc_ws,
            "nurse": nurse_ws,
        }
        rows = {
            "doc": _row(agent_id="doc"),
            "nurse": _row(agent_id="nurse"),
            "nested": _row(agent_id="nested", kind="team"),
        }
        registry = SimpleNamespace(
            teams=SimpleNamespace(visible_member_ids=lambda _id: ["doc", "nurse", "nested"]),
            get_row=lambda agent_id: rows.get(agent_id),
            workspace_for_agent=lambda agent_id: workspaces.get(agent_id),
        )
        payload = await team_host_welcome_payload(_row(agent_id="host", kind="team"), registry)

    assert payload["welcome_message"]["zh"] == "团队介绍"
    titles = [card["title"]["zh"] for card in payload["quick_prompts"]]
    assert titles == ["鉴别诊断", "用药提醒", "健康打卡"]
    assert "主持卡" not in titles
    assert [card["expert"] for card in payload["quick_prompts"]] == [
        "doc",
        "doc",
        "nurse",
    ]
    assert [card["agent_id"] for card in payload["quick_prompts"]] == [
        "doc",
        "doc",
        "nurse",
    ]


@pytest.mark.asyncio
async def test_team_welcome_prefers_db_welcome_message() -> None:
    with tempfile.TemporaryDirectory() as host_dir:
        host_ws = _workspace(host_dir)
        await _write_manifest(
            host_ws,
            {"welcome_message": {"zh": "清单介绍", "en": "Manifest"}, "quick_prompts": []},
        )
        registry = SimpleNamespace(
            teams=SimpleNamespace(visible_member_ids=lambda _id: []),
            get_row=lambda _id: None,
            workspace_for_agent=lambda _id: host_ws,
        )
        payload = await team_host_welcome_payload(
            _row(agent_id="host", kind="team", welcome="数据库介绍"),
            registry,
        )
    assert payload["welcome_message"] == {"zh": "数据库介绍", "en": "数据库介绍"}
    assert payload["quick_prompts"] == []


@pytest.mark.asyncio
async def test_team_welcome_uses_member_default_cards_when_workspace_has_none() -> None:
    with tempfile.TemporaryDirectory() as empty_dir:
        empty_ws = _workspace(empty_dir)
        registry = SimpleNamespace(
            teams=SimpleNamespace(visible_member_ids=lambda _id: ["doc", "clone"]),
            get_row=lambda agent_id: _row(agent_id=agent_id),
            workspace_for_agent=lambda _id: empty_ws,
        )
        payload = await team_host_welcome_payload(_row(agent_id="host", kind="team"), registry)

    titles = [card["title"]["zh"] for card in payload["quick_prompts"]]
    experts = [card["expert"] for card in payload["quick_prompts"]]
    assert titles
    assert set(experts) == {"doc", "clone"}
    assert experts.count("doc") == experts.count("clone")
