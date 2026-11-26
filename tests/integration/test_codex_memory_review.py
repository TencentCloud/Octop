"""External Codex model selection is scoped to the space token and its billing user."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from octop.infra.agents import codex_memory_review as review
from octop.infra.agents import memory_sharing
from tests.support.auth import create_provider


async def test_terminal_model_choice_and_verified_review(env, monkeypatch):
    client, _, auth = env
    await create_provider(
        client,
        auth,
        name="terminal-llm",
        base_url="https://model.example/v1",
        models=[
            {
                "id": "light",
                "enabled": True,
                "reasoning_config": {"supported": True, "toggle": True, "adapter": "thinking"},
            }
        ],
    )
    record = {"token_id": "mt_test", "scopes": ["read", "write"]}
    monkeypatch.setattr(
        memory_sharing,
        "list_tokens_in",
        lambda _user, space: {"tokens": [record] if space == "work" else []},
    )
    path = "/api/memory-mcp/tokens/mt_test/codex-model"
    ref = "terminal-llm/light"
    assert (
        await client.put(path + "?space_id=other", headers=auth, json={"model": ref})
    ).status_code == 403
    assert (
        await client.put(path + "?space_id=work", headers=auth, json={"model": "absent/no"})
    ).status_code == 400
    assert (await client.put(path + "?space_id=work", headers=auth, json={"model": ref})).is_success
    saved = (await client.get(path + "?space_id=work", headers=auth)).json()
    assert saved["model"] == ref and saved["mode"] == "octop" and saved["mode_since"]
    phrase = "Use metric units for workshop projects."
    event = "evt_123456789abc"
    second_phrase = "Use tagged releases for workshop tools."
    facts = [
        {
            "event_id": event,
            "kind": "Preference",
            "quote": phrase,
            "assertion": "Workshop projects use metric units.",
        },
        {
            "event_id": event,
            "kind": "Decision",
            "quote": second_phrase,
            "assertion": "Workshop tools use tagged releases.",
        },
    ]
    source = {
        "space_id": "work",
        "token_id": "mt_test",
        "messages": [{"id": event, "text": phrase + " " + second_phrase}],
    }
    calls = []

    def call_memory(_client, tool, arguments):
        calls.append((tool, arguments))
        if tool == "memory_codex_terminal_identity":
            assert not arguments
            return {"space_id": source["space_id"], "token_id": source["token_id"]}
        if tool == "memory_codex_review_evidence":
            return source
        assert arguments == {"facts": facts, "review_model": ref}
        return {"candidate_ids": ["candidate", "second"], "status": "needs_review"}

    monkeypatch.setattr(review, "_call_memory", call_memory)
    model = MagicMock()
    model.extra_body = {"keep": 1}
    model.bind.return_value.invoke.return_value = SimpleNamespace(text=json.dumps({"facts": facts}))
    make_model = MagicMock(return_value=model)
    monkeypatch.setattr(review, "build_probe_chat_model", make_model)
    request = {"session_id": "codex:session", "turn_id": "one", "event_ids": [event]}
    endpoint = "/api/memory-mcp/codex-review"
    assert (await client.post(endpoint, json=request)).status_code == 401
    bearer = {"authorization": "Bearer omcp_test_only"}
    sync = "/api/memory-mcp/codex-config"
    assert (await client.post(sync, json={})).status_code == 401
    assert (await client.post(sync, headers=bearer, json={})).json() == {"revision": None}
    publish = path + "?space_id=work&apply=true"
    published = (await client.put(publish, headers=auth, json={"model": ref})).json()
    version = published["published_at"]
    assert (
        version
        and (await client.put(publish, headers=auth, json={"model": ref})).json() == published
    )
    assert (await client.post(sync, headers=bearer, json={})).json() == {
        "revision": version,
        "mode": "octop",
    }
    source["token_id"] = "mt_other"
    assert (await client.post(sync, headers=bearer, json={"applied_revision": version})).json() == {
        "revision": None
    }
    assert (await client.post(endpoint, headers=bearer, json=request)).status_code == 403
    make_model.assert_not_called()
    source["token_id"] = "mt_test"
    assert (await client.post(sync, headers=bearer, json={"applied_revision": version})).is_success
    for _ in range(2):
        result = await client.post(endpoint, headers=bearer, json=request)
        assert result.status_code == 200, result.text
        assert result.json() == {
            "model": ref,
            "candidate_id": "candidate",
            "candidate_ids": ["candidate", "second"],
            "status": "needs_review",
        }
    make_model.assert_called_once()
    assert model.bind.call_args.kwargs["extra_body"] == {
        "keep": 1,
        "thinking": {"type": "disabled"},
    }
    assert make_model.call_args.kwargs["model_id"] == "light"
    assert [name for name, _ in calls].count("memory_propose") == 1
    for batch in ([facts[0], {**facts[1], "quote": "invented"}], facts * 2):
        model.bind.return_value.invoke.return_value.text = json.dumps({"facts": batch})
        invalid = await client.post(
            endpoint, headers=bearer, json={**request, "turn_id": "invalid"}
        )
        assert invalid.status_code == 502
    model.bind.return_value.invoke.return_value.text = '{"facts":[]}'
    skipped = await client.post(endpoint, headers=bearer, json={**request, "turn_id": "skip"})
    assert skipped.json() == {"status": "skipped", "model": ref}
    assert [name for name, _ in calls].count("memory_propose") == 1
    model.bind.return_value.invoke.side_effect = [
        SimpleNamespace(text=json.dumps({"facts": [{**facts[0], "assertion": phrase}]})),
        SimpleNamespace(text=json.dumps({"facts": facts})),
    ]
    repaired = await client.post(endpoint, headers=bearer, json={**request, "turn_id": "repair"})
    assert repaired.json()["candidate_ids"] == ["candidate", "second"]
    assert [name for name, _ in calls].count("memory_propose") == 2
    monkeypatch.setattr(
        memory_sharing, "codex_status", lambda *_: {"observed": None, "last_run": None}
    )
    observed = await client.get(
        path.replace("codex-model", "codex-status") + "?space_id=work", headers=auth
    )
    assert observed.json()["last_run"]["model"] == ref
    assert observed.json()["acknowledgement"]["revision"] == version
    changed = await client.put(
        path + "?space_id=work", headers=auth, json={"model": None, "mode": "server"}
    )
    assert changed.is_success
    assert (await client.get(path + "?space_id=work", headers=auth)).json()["mode"] == "server"
    assert (await client.post(endpoint, headers=bearer, json=request)).status_code == 403
