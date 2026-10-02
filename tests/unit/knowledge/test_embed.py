from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from octop.infra.knowledge import embed
from octop.infra.knowledge.index import KnowledgeIndex


@pytest.mark.parametrize(
    ("base_url", "model"),
    [
        ("https://example.test/v1/", "embed-1"),
        ("https://ark.cn-beijing.volces.com/api/v3/", "doubao-embedding-large-text-250515"),
    ],
)
def test_remote_embedding_routes_to_provider_embeddings_endpoint(
    base_url, model, monkeypatch
) -> None:
    provider = SimpleNamespace(base_url=base_url, api_key="secret")
    services = SimpleNamespace(
        settings_repo=SimpleNamespace(
            get=lambda key: {
                "knowledge_embedding_backend": "remote",
                "knowledge_embedding_model": model,
                "knowledge_embedding_provider_id": "7",
            }.get(key)
        ),
        provider_repo=SimpleNamespace(
            get=lambda provider_id: provider if provider_id == 7 else None
        ),
    )
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"embedding": [1.0, 2.0]}]}

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, url, *, headers, json):
            captured.update(url=url, headers=headers, json=json)
            return Response()

    monkeypatch.setattr(embed.httpx, "Client", lambda **_kwargs: Client())

    assert embed.embed_knowledge_texts(services, ["hello"]) == [[1.0, 2.0]]
    assert captured["url"] == f"{base_url.rstrip('/')}/embeddings"
    assert captured["json"] == {"model": model, "input": ["hello"]}
    assert captured["headers"]["Authorization"] == "Bearer secret"


def test_remote_embedding_merges_provider_extra_headers(monkeypatch) -> None:
    provider = SimpleNamespace(
        base_url="https://example.test/v1/",
        api_key="secret",
        extra_json='{"headers": {"X-Custom": "1"}}',
    )
    services = SimpleNamespace(
        settings_repo=SimpleNamespace(
            get=lambda key: {
                "knowledge_embedding_backend": "remote",
                "knowledge_embedding_model": "embed-1",
                "knowledge_embedding_provider_id": "7",
            }.get(key)
        ),
        provider_repo=SimpleNamespace(
            get=lambda provider_id: provider if provider_id == 7 else None
        ),
    )
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"embedding": [0.5]}]}

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, url, *, headers, json):
            captured.update(url=url, headers=headers, json=json)
            return Response()

    monkeypatch.setattr(embed.httpx, "Client", lambda **_kwargs: Client())

    assert embed.embed_knowledge_texts(services, ["hello"]) == [[0.5]]
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["headers"]["X-Custom"] == "1"


def test_remote_embedding_batches_large_input(monkeypatch) -> None:
    provider = SimpleNamespace(base_url="https://example.test/v1/", api_key="secret")
    services = SimpleNamespace(
        settings_repo=SimpleNamespace(
            get=lambda key: {
                "knowledge_embedding_backend": "remote",
                "knowledge_embedding_model": "embed-1",
                "knowledge_embedding_provider_id": "7",
            }.get(key)
        ),
        provider_repo=SimpleNamespace(
            get=lambda provider_id: provider if provider_id == 7 else None
        ),
    )
    calls: list[dict] = []

    class Response:
        def __init__(self, batch: list[str]) -> None:
            # One embedding per input, tagged with the input's global position.
            self._data = [{"embedding": [float(t.split("-")[1])]} for t in batch]

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": self._data}

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, url, *, headers, json):
            calls.append({"url": url, "json": json})
            return Response(json["input"])

    monkeypatch.setattr(embed.httpx, "Client", lambda **_kwargs: Client())

    texts = [f"chunk-{i}" for i in range(45)]
    result = embed.embed_knowledge_texts(services, texts)

    # AssertiveProviders cap at 20 -> 45 inputs => 3 requests (20/20/5).
    assert len(calls) == 3
    assert calls[0]["json"]["input"] == texts[0:20]
    assert calls[1]["json"]["input"] == texts[20:40]
    assert calls[2]["json"]["input"] == texts[40:45]
    # Merged vectors stay aligned with input order.
    assert len(result) == 45
    assert result == [[float(i)] for i in range(45)]


@pytest.mark.parametrize(
    ("base_url", "model"),
    [
        ("https://ark.cn-beijing.volces.com/api/v3/", "doubao-embedding-vision-251215"),
        (
            "https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal/",
            "doubao-embedding-vision-251215",
        ),
        ("https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal", "ep-test"),
    ],
)
def test_volcengine_embeddings_preserve_chunks_and_support_index_search(
    base_url, model, tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    provider = SimpleNamespace(
        base_url=base_url, api_key="secret", extra_json='{"headers": {"X-Custom": "1"}}'
    )
    services = SimpleNamespace(
        settings_repo=SimpleNamespace(
            get=lambda key: {
                "knowledge_embedding_backend": "remote",
                "knowledge_embedding_model": model,
                "knowledge_embedding_provider_id": "7",
            }.get(key)
        ),
        provider_repo=SimpleNamespace(get=lambda _id: provider),
    )
    texts = [f"chunk-{i}" for i in range(21)]
    calls = []

    def respond(request):
        assert str(request.url) == (
            "https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal"
        )
        assert request.headers["Authorization"] == "Bearer secret"
        assert request.headers["X-Custom"] == "1"
        body = json.loads(request.content)
        assert body["model"] == model
        assert body["encoding_format"] == "float"
        assert len(body["input"]) == 1
        assert body["input"][0]["type"] == "text"
        text = body["input"][0]["text"]
        calls.append(text)
        ordinal = 7 if text == "query" else int(text.split("-")[1])
        vector = [float(ordinal), 1.0]
        return httpx.Response(200, json={"data": {"embedding": vector}})

    client_class = httpx.Client
    monkeypatch.setattr(
        embed.httpx,
        "Client",
        lambda **kwargs: client_class(transport=httpx.MockTransport(respond), **kwargs),
    )
    vectors = embed.embed_knowledge_texts(services, texts)
    assert calls == texts
    assert vectors == [[float(i), 1.0] for i in range(21)]

    index = KnowledgeIndex("kb-1299")
    index.replace_doc_chunks("doc-1299", texts, vectors)
    query_vectors = embed.embed_knowledge_texts(services, ["query"])
    assert calls == [*texts, "query"]
    assert index.search(query_vectors[0], k=1)[0].text == "chunk-7"
