"""External Codex model selection is scoped to the space token and its billing user."""

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
        models=[{"id": "light", "enabled": True}],
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
    assert (
        await client.put(path + "?space_id=work", headers=auth, json={"model": ref})
    ).json() == {"model": ref}
    assert (await client.get(path + "?space_id=work", headers=auth)).json() == {"model": ref}
    phrase = "Use metric units for workshop projects."
    event = "evt_123456789abc"
    source = {
        "space_id": "work",
        "token_id": "mt_test",
        "messages": [{"id": event, "text": phrase}],
    }
    calls = []

    def call_memory(_client, tool, arguments):
        calls.append((tool, arguments))
        if tool == "memory_codex_review_evidence":
            return source
        assert arguments == {
            "event_id": event,
            "kind": "Preference",
            "quote": phrase,
            "review_model": ref,
        }
        return {"candidate_id": "candidate", "status": "needs_review"}

    monkeypatch.setattr(review, "_call_memory", call_memory)
    model = MagicMock()
    model.bind.return_value.invoke.return_value = SimpleNamespace(
        text='{"event_id":"' + event + '","kind":"Preference","quote":"' + phrase + '"}'
    )
    make_model = MagicMock(return_value=model)
    monkeypatch.setattr(review, "build_probe_chat_model", make_model)
    request = {"session_id": "codex:session", "turn_id": "one", "event_ids": [event]}
    endpoint = "/api/memory-mcp/codex-review"
    assert (await client.post(endpoint, json=request)).status_code == 401
    bearer = {"authorization": "Bearer omcp_test_only"}
    source["token_id"] = "mt_other"
    assert (await client.post(endpoint, headers=bearer, json=request)).status_code == 403
    make_model.assert_not_called()
    source["token_id"] = "mt_test"
    for _ in range(2):
        result = await client.post(endpoint, headers=bearer, json=request)
        assert result.status_code == 200, result.text
        assert result.json() == {
            "model": ref,
            "candidate_id": "candidate",
            "status": "needs_review",
        }
    make_model.assert_called_once()
    assert make_model.call_args.kwargs["model_id"] == "light"
    assert [name for name, _ in calls].count("memory_propose") == 1
    assert (
        await client.put(path + "?space_id=work", headers=auth, json={"model": None})
    ).json() == {"model": None}
    assert (await client.post(endpoint, headers=bearer, json=request)).status_code == 403
