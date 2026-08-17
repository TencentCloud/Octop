from __future__ import annotations

from types import SimpleNamespace

from octop.infra.knowledge import embed


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
