from __future__ import annotations

import json
from collections.abc import Iterator
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

from octop.infra.agents.providers.codex_apply import CODEX_PROVIDER_NAME
from octop.infra.agents.providers.codex_oauth import CODEX_ATTRIBUTION_VERSION
from octop.infra.agents.providers.probe import (
    _is_codex_base_url,
    fetch_openai_compatible_models,
)


@pytest.fixture
def model_server(
    tmp_path: Path, request: pytest.FixtureRequest
) -> Iterator[tuple[str, list[tuple[str, dict[str, str]]]]]:
    (tmp_path / "models").write_text(json.dumps(request.param), encoding="utf-8")
    requests: list[tuple[str, dict[str, str]]] = []

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=str(tmp_path), **kwargs)

        def do_GET(self) -> None:
            requests.append((self.path, dict(self.headers)))
            super().do_GET()

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", requests
        finally:
            server.shutdown()
            thread.join()


@pytest.mark.asyncio
@pytest.mark.parametrize("model_server", [{"models": []}], indirect=True)
async def test_codex_models_request_uses_attribution_version(model_server) -> None:
    base_url, requests = model_server
    await fetch_openai_compatible_models(
        base_url=base_url,
        api_key="test-access-token",
        provider_name=CODEX_PROVIDER_NAME,
        extra_headers={"chatgpt-account-id": "test-account", "version": CODEX_ATTRIBUTION_VERSION},
    )
    path, headers = requests[0]
    assert urlsplit(path).path == "/models"
    assert parse_qs(urlsplit(path).query) == {"client_version": [CODEX_ATTRIBUTION_VERSION]}
    assert headers["Authorization"] == "Bearer test-access-token"
    assert headers["chatgpt-account-id"] == "test-account"
    assert headers["version"] == CODEX_ATTRIBUTION_VERSION


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model_server",
    [
        {
            "models": [
                {"slug": " gpt-5.4 ", "display_name": " GPT-5.4 "},
                {"slug": "gpt-5.4", "display_name": "Duplicate"},
                {"slug": "gpt-5.3-codex", "display_name": "GPT-5.3 Codex"},
                {"slug": "gpt-5.4-mini"},
                {"slug": ""},
                {"slug": 123},
                {"id": "wrong-protocol"},
                None,
            ]
        }
    ],
    indirect=True,
)
async def test_codex_models_normalizes_slugs_and_display_names(model_server) -> None:
    base_url, _ = model_server
    result = await fetch_openai_compatible_models(
        base_url=base_url, api_key="test-access-token", provider_name=CODEX_PROVIDER_NAME
    )
    assert result == {
        "ok": True,
        "models": [
            {"id": "gpt-5.3-codex", "name": "GPT-5.3 Codex"},
            {"id": "gpt-5.4", "name": "GPT-5.4"},
            {"id": "gpt-5.4-mini", "name": "gpt-5.4-mini"},
        ],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("model_server", [{"models": []}], indirect=True)
async def test_codex_models_accepts_empty_list(model_server) -> None:
    base_url, _ = model_server
    result = await fetch_openai_compatible_models(
        base_url=base_url, api_key="test-access-token", provider_name=CODEX_PROVIDER_NAME
    )
    assert result == {"ok": True, "models": []}


@pytest.mark.asyncio
@pytest.mark.parametrize("model_server", [{"data": []}, {"models": {}}], indirect=True)
@pytest.mark.parametrize(
    ("locale", "expected_error"),
    [
        ("en", "Invalid Codex model list (expected models entries with slug identifiers)."),
        ("zh", "Codex 模型列表格式无效（应包含 models 列表和 slug 标识）。"),
    ],
)
async def test_codex_models_rejects_invalid_collection(
    model_server, locale, expected_error
) -> None:
    base_url, _ = model_server
    result = await fetch_openai_compatible_models(
        base_url=base_url,
        api_key="test-access-token",
        provider_name=CODEX_PROVIDER_NAME,
        locale=locale,
    )
    assert result == {"ok": False, "error": expected_error}


@pytest.mark.asyncio
@pytest.mark.parametrize("model_server", [{"data": [{"id": "gpt-4o"}]}], indirect=True)
async def test_openai_models_keeps_original_protocol(model_server) -> None:
    base_url, requests = model_server
    result = await fetch_openai_compatible_models(base_url=base_url, api_key="test-api-key")
    assert result == {"ok": True, "models": [{"id": "gpt-4o", "name": "gpt-4o"}]}
    assert requests[0][0] == "/models"


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://chatgpt.com/backend-api/codex", True),
        ("https://chatgpt.com/backend-api/codex/", True),
        ("https://example.com/chatgpt.com/backend-api/codex", False),
        ("https://chatgpt.com/backend-api/codex-proxy", False),
        ("https://chatgpt.com.example.com/backend-api/codex", False),
    ],
)
def test_codex_base_url_requires_matching_host_and_path(base_url: str, expected: bool) -> None:
    assert _is_codex_base_url(base_url) is expected
