"""Knowledge-graph settings and LLM extraction of entities and relations."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage

from octop.infra.agents.providers.model_flags import is_chat_eligible_model
from octop.infra.agents.providers.probe import build_probe_chat_model
from octop.infra.knowledge.graph_store import ChunkEntity, ChunkGraph, ChunkRelation, entity_key
from octop.infra.utils.llm_text import llm_text_content

_ENABLED_KEY = "knowledge_graph_enabled"
_PROVIDER_ID_KEY = "knowledge_graph_provider_id"
_MODEL_KEY = "knowledge_graph_model"

ENTITY_TYPES = (
    "person",
    "organization",
    "location",
    "product",
    "technology",
    "event",
    "document",
    "concept",
    "time",
    "other",
)
MAX_ENTITIES_PER_CHUNK = 15
MAX_RELATIONS_PER_CHUNK = 20
_MAX_NAME_CHARS = 80
_MAX_LABEL_CHARS = 60
_MAX_DESCRIPTION_CHARS = 300

_PROMPT = """You extract a knowledge graph from one passage of a document.

Return ONLY a JSON object, with no prose and no code fence:
{{"entities":[{{"name":"...","type":"...","description":"..."}}],
"relations":[{{"source":"...","target":"...","relation":"...","description":"...","strength":7}}]}}

Rules:
- Entities are the people, organizations, places, products, systems, events, documents,
  concepts and dates the passage is actually about. Skip pronouns and generic words.
- "type" is one of: {types}.
- Use each entity's full name as written in the passage, and reuse exactly that spelling
  in "source" and "target". Both ends of a relation must be listed entities.
- "relation" is a short phrase naming how source relates to target; "description" is one
  sentence grounded in the passage.
- "strength" is an integer from 1 to 10: how explicitly the passage states the relation.
- Write names, relations and descriptions in the language of the passage.
- At most {max_entities} entities and {max_relations} relations.
- If nothing qualifies, return {{"entities":[],"relations":[]}}.

Document: {filename}
Passage:
\"\"\"
{text}
\"\"\"
"""


def _as_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() == "true"


def _provider(provider_repo: Any, provider_id: str) -> Any | None:
    if provider_repo is None or not provider_id.isdigit():
        return None
    return provider_repo.get(int(provider_id))


def graph_models(provider: Any) -> list[dict[str, str]]:
    """Chat models of *provider* that can run extraction."""
    if not (provider and provider.enabled and provider.api_key and provider.base_url):
        return []
    return [
        {"id": str(model["id"]), "name": str(model.get("name") or model["id"])}
        for model in provider.get_models()
        if str(model.get("id") or "").strip()
        and is_chat_eligible_model(
            model, provider_name=provider.name, provider_api_key=provider.api_key
        )
    ]


def _ready(provider: Any | None, model_id: str) -> bool:
    return bool(model_id) and any(model["id"] == model_id for model in graph_models(provider))


def get_graph_capability(settings_get: Any, provider_repo: Any = None) -> dict[str, Any]:
    """Return the stored extraction model and whether graphs can be built now."""
    enabled = _as_bool(settings_get(_ENABLED_KEY))
    provider_id = (settings_get(_PROVIDER_ID_KEY) or "").strip()
    model = (settings_get(_MODEL_KEY) or "").strip()
    ready = _ready(_provider(provider_repo, provider_id), model)
    return {
        "enabled": enabled,
        "provider_id": provider_id,
        "model": model,
        "ready": ready,
        "usable": enabled and ready,
    }


def set_graph_settings(
    settings_set: Any,
    *,
    enabled: bool,
    provider_id: str | None,
    model: str | None,
    provider_repo: Any = None,
) -> None:
    """Persist the extraction model; enabling requires a ready chat model."""
    selected_provider = (provider_id or "").strip()
    selected_model = (model or "").strip()
    if enabled and not _ready(_provider(provider_repo, selected_provider), selected_model):
        raise ValueError("knowledge graph model is not available on the selected provider")
    settings_set(_ENABLED_KEY, "true" if enabled else "false")
    settings_set(_PROVIDER_ID_KEY, selected_provider)
    settings_set(_MODEL_KEY, selected_model)


def _clip(value: object, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit].strip()


def _strength(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return 5.0
    try:
        number = float(value)
    except ValueError:
        return 5.0
    return min(max(number, 1.0), 10.0)


def _decode(reply: str) -> dict[str, Any]:
    # Models often wrap the object in a code fence or a sentence; take the object itself.
    text = reply.strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("knowledge graph extraction returned no JSON object")
    try:
        decoded = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError("knowledge graph extraction returned invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError("knowledge graph extraction returned no JSON object")
    return decoded


def parse_extraction(reply: str, *, ordinal: int) -> ChunkGraph:
    """Turn one model reply into validated entities and relations."""
    decoded = _decode(reply)
    entities: dict[str, ChunkEntity] = {}
    raw_entities = decoded.get("entities")
    for item in raw_entities if isinstance(raw_entities, list) else []:
        if not isinstance(item, dict):
            continue
        name = _clip(item.get("name"), _MAX_NAME_CHARS)
        key = entity_key(name)
        if len(key) < 2 or key in entities or len(entities) >= MAX_ENTITIES_PER_CHUNK:
            continue
        kind = _clip(item.get("type"), 30).lower()
        entities[key] = ChunkEntity(
            name=name,
            type=kind if kind in ENTITY_TYPES else "other",
            description=_clip(item.get("description"), _MAX_DESCRIPTION_CHARS),
        )
    relations: dict[tuple[str, str, str], ChunkRelation] = {}
    raw_relations = decoded.get("relations")
    for item in raw_relations if isinstance(raw_relations, list) else []:
        if not isinstance(item, dict) or len(relations) >= MAX_RELATIONS_PER_CHUNK:
            continue
        source = entity_key(_clip(item.get("source"), _MAX_NAME_CHARS))
        target = entity_key(_clip(item.get("target"), _MAX_NAME_CHARS))
        label = _clip(item.get("relation"), _MAX_LABEL_CHARS)
        # A relation to something the model did not list as an entity is a guess; drop it.
        if source not in entities or target not in entities or source == target or not label:
            continue
        relations.setdefault(
            (source, target, label.casefold()),
            ChunkRelation(
                source=entities[source].name,
                target=entities[target].name,
                label=label,
                description=_clip(item.get("description"), _MAX_DESCRIPTION_CHARS),
                strength=_strength(item.get("strength")),
            ),
        )
    return ChunkGraph(
        ordinal=ordinal,
        entities=tuple(entities.values()),
        relations=tuple(relations.values()),
    )


class GraphExtractor:
    """Extract one chunk's entities and relations with the configured chat model."""

    def __init__(self, services: Any) -> None:
        capability = get_graph_capability(
            services.settings_repo.get, getattr(services, "provider_repo", None)
        )
        if not capability["usable"]:
            raise RuntimeError("knowledge graph extraction is not ready")
        provider = _provider(services.provider_repo, capability["provider_id"])
        self._model = build_probe_chat_model(provider, model_id=capability["model"])

    def __call__(self, *, filename: str, ordinal: int, text: str) -> ChunkGraph:
        prompt = _PROMPT.format(
            types=", ".join(ENTITY_TYPES),
            max_entities=MAX_ENTITIES_PER_CHUNK,
            max_relations=MAX_RELATIONS_PER_CHUNK,
            filename=filename,
            text=text,
        )
        reply = llm_text_content(self._model.invoke([HumanMessage(content=prompt)]))
        return parse_extraction(reply, ordinal=ordinal)
