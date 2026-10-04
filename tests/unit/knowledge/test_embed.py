from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from octop.infra.knowledge import embed


@pytest.mark.parametrize("batch_limit", [1, 20])
def test_remote_embeddings_reject_mixed_dimensions(monkeypatch, batch_limit) -> None:
    monkeypatch.setattr(embed, "_KNOWLEDGE_EMBEDDING_BATCH_LIMIT", batch_limit)
    vectors = iter([[1.0, 0.0], [1.0, 0.0, 0.0]])

    def handle(request):
        inputs = json.loads(request.content)["input"]
        return httpx.Response(200, json={"data": [{"embedding": next(vectors)} for _ in inputs]})

    with (
        httpx.Client(transport=httpx.MockTransport(handle)) as client,
        pytest.raises(RuntimeError, match="dimension"),
    ):
        embed._embed_remote_batched(client, "https://embedding.test", {}, "model", ["a", "b"])


@pytest.mark.parametrize("vectors", [[[]], [[1.0, 0.0], []]])
def test_remote_embeddings_reject_empty_vectors(vectors) -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, json={"data": [{"embedding": v} for v in vectors]})
    )
    with (
        httpx.Client(transport=transport) as client,
        pytest.raises(RuntimeError, match="dimensions"),
    ):
        embed._embed_remote_batched(
            client, "https://embedding.test", {}, "model", ["text"] * len(vectors)
        )


def test_remote_embedding_dimensions_preserve_valid_batched_results(monkeypatch) -> None:
    monkeypatch.setattr(embed, "_KNOWLEDGE_EMBEDDING_BATCH_LIMIT", 1)
    expected = {"a": [1.0, 0.0], "b": [0.0, 1.0]}

    def handle(request):
        inputs = json.loads(request.content)["input"]
        return httpx.Response(200, json={"data": [{"embedding": expected[t]} for t in inputs]})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        assert embed._embed_remote_batched(
            client, "https://embedding.test", {}, "model", ["a", "b"]
        ) == [[1.0, 0.0], [0.0, 1.0]]


def test_remote_embedding_routes_to_provider_embeddings_endpoint(monkeypatch) -> None:
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
    assert captured["url"] == "https://example.test/v1/embeddings"
    assert captured["json"] == {"model": "embed-1", "input": ["hello"]}
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
