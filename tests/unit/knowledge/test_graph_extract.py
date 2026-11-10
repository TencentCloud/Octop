"""Unit tests for knowledge-graph settings and reply parsing."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from octop.infra.knowledge import graph_extract
from octop.infra.knowledge.graph_extract import (
    MAX_ENTITIES_PER_CHUNK,
    GraphExtractor,
    get_graph_capability,
    graph_models,
    parse_extraction,
    set_graph_settings,
)


def _provider(*, enabled: bool = True, api_key: str = "key") -> SimpleNamespace:
    return SimpleNamespace(
        id=7,
        name="acme",
        enabled=enabled,
        api_key=api_key,
        base_url="https://llm.example/v1",
        get_models=lambda: [
            {"id": "chat-1", "name": "Chat One"},
            {"id": "embed-1", "name": "Embed", "type": "embedding"},
        ],
    )


def _repo(provider: SimpleNamespace | None) -> SimpleNamespace:
    return SimpleNamespace(get=lambda provider_id: provider if provider_id == 7 else None)


def test_graph_models_lists_only_chat_models_of_a_usable_provider() -> None:
    assert graph_models(_provider()) == [{"id": "chat-1", "name": "Chat One"}]
    assert graph_models(_provider(enabled=False)) == []
    assert graph_models(_provider(api_key="")) == []
    assert graph_models(None) == []


def test_capability_is_usable_only_when_enabled_with_a_ready_model() -> None:
    settings = {
        "knowledge_graph_enabled": "true",
        "knowledge_graph_provider_id": "7",
        "knowledge_graph_model": "chat-1",
    }

    assert get_graph_capability(settings.get, _repo(_provider())) == {
        "enabled": True,
        "provider_id": "7",
        "model": "chat-1",
        "ready": True,
        "usable": True,
    }
    assert get_graph_capability(settings.get, _repo(None))["usable"] is False
    settings["knowledge_graph_model"] = "embed-1"
    assert get_graph_capability(settings.get, _repo(_provider()))["ready"] is False
    assert get_graph_capability({}.get)["enabled"] is False


def test_enabling_requires_a_chat_model_and_disabling_does_not() -> None:
    settings: dict[str, str] = {}

    with pytest.raises(ValueError, match="knowledge graph model is not available"):
        set_graph_settings(
            settings.__setitem__,
            enabled=True,
            provider_id="7",
            model="embed-1",
            provider_repo=_repo(_provider()),
        )
    assert settings == {}

    set_graph_settings(
        settings.__setitem__,
        enabled=True,
        provider_id=" 7 ",
        model="chat-1",
        provider_repo=_repo(_provider()),
    )
    assert settings == {
        "knowledge_graph_enabled": "true",
        "knowledge_graph_provider_id": "7",
        "knowledge_graph_model": "chat-1",
    }

    set_graph_settings(settings.__setitem__, enabled=False, provider_id=None, model=None)
    assert settings["knowledge_graph_enabled"] == "false"


def test_parse_reads_an_object_wrapped_in_a_fence_and_prose() -> None:
    reply = (
        "Here is the graph:\n```json\n"
        + json.dumps(
            {
                "entities": [
                    {"name": "Alice  Chen", "type": "Person", "description": "Leads Apollo."},
                    {"name": "Apollo", "type": "spaceship", "description": ""},
                ],
                "relations": [
                    {
                        "source": "alice chen",
                        "target": "Apollo",
                        "relation": "leads",
                        "description": "Alice leads Apollo.",
                        "strength": 42,
                    }
                ],
            }
        )
        + "\n```"
    )

    graph = parse_extraction(reply, ordinal=3)

    assert graph.ordinal == 3
    assert [(item.name, item.type) for item in graph.entities] == [
        ("Alice Chen", "person"),
        ("Apollo", "other"),
    ]
    relation = graph.relations[0]
    assert (relation.source, relation.target, relation.label) == ("Alice Chen", "Apollo", "leads")
    assert relation.strength == 10.0


def test_parse_drops_relations_the_passage_cannot_back() -> None:
    reply = json.dumps(
        {
            "entities": [{"name": "Alice"}, {"name": "Bob"}, {"name": "x"}, "junk"],
            "relations": [
                {"source": "Alice", "target": "Carol", "relation": "knows"},
                {"source": "Alice", "target": "Alice", "relation": "is"},
                {"source": "Alice", "target": "Bob", "relation": ""},
                {"source": "Alice", "target": "Bob", "relation": "manages", "strength": "high"},
                {"source": "Alice", "target": "Bob", "relation": "Manages"},
                None,
            ],
        }
    )

    graph = parse_extraction(reply, ordinal=0)

    assert [item.name for item in graph.entities] == ["Alice", "Bob"]
    assert [(item.label, item.strength) for item in graph.relations] == [("manages", 5.0)]


def test_parse_caps_entities_per_chunk() -> None:
    reply = json.dumps({"entities": [{"name": f"Entity {n}"} for n in range(40)]})

    assert len(parse_extraction(reply, ordinal=0).entities) == MAX_ENTITIES_PER_CHUNK


def test_parse_accepts_an_empty_graph() -> None:
    graph = parse_extraction('{"entities":[],"relations":[]}', ordinal=0)

    assert graph.entities == () and graph.relations == ()


@pytest.mark.parametrize("reply", ["", "no json here", "{not json}", "[1, 2]"])
def test_parse_rejects_replies_without_a_json_object(reply: str) -> None:
    with pytest.raises(ValueError, match="knowledge graph extraction returned"):
        parse_extraction(reply, ordinal=0)


def test_extractor_refuses_to_start_without_a_ready_model() -> None:
    services = SimpleNamespace(
        settings_repo=SimpleNamespace(get=lambda _key: None), provider_repo=_repo(None)
    )

    with pytest.raises(RuntimeError, match="knowledge graph extraction is not ready"):
        GraphExtractor(services)


def test_extractor_sends_the_passage_and_parses_the_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = {
        "knowledge_graph_enabled": "true",
        "knowledge_graph_provider_id": "7",
        "knowledge_graph_model": "chat-1",
    }
    prompts: list[str] = []

    class _Model:
        def invoke(self, messages: list[object]) -> SimpleNamespace:
            prompts.append(str(messages[0].content))  # type: ignore[attr-defined]
            return SimpleNamespace(content='{"entities":[{"name":"Apollo","type":"product"}]}')

    built: list[tuple[object, str]] = []

    def build(provider: object, *, model_id: str) -> _Model:
        built.append((provider, model_id))
        return _Model()

    monkeypatch.setattr(graph_extract, "build_probe_chat_model", build)
    provider = _provider()
    services = SimpleNamespace(
        settings_repo=SimpleNamespace(get=settings.get), provider_repo=_repo(provider)
    )

    graph = GraphExtractor(services)(filename="plan.md", ordinal=2, text="Apollo ships in May.")

    assert built == [(provider, "chat-1")]
    assert "Document: plan.md" in prompts[0]
    assert "Apollo ships in May." in prompts[0]
    assert graph.ordinal == 2
    assert [item.name for item in graph.entities] == ["Apollo"]
