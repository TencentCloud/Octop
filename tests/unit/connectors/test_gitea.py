"""Gitea REST contract, credential validation, and gateway tools."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from octop.config import OctopConfig
from octop.infra.connectors.builder import validate_create_credentials
from octop.infra.connectors.catalog import catalog_entry_to_dict, get_catalog_entry
from octop.infra.connectors.gateway.adapters import gitea
from octop.infra.connectors.gateway.protocol import handle_mcp_request
from octop.infra.connectors.probe import probe_connector
from octop.infra.errors import OctopError

CREDS = {"base_url": "https://gitea.example.com", "token": "gitea-test-token"}


@pytest.fixture
def mock_http(monkeypatch: pytest.MonkeyPatch) -> Callable[..., list[httpx.Request]]:
    original_client = httpx.Client

    def install(
        payload: Any = None, *, status: int = 200, text: str | None = None
    ) -> list[httpx.Request]:
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            if text is not None:
                return httpx.Response(status, text=text)
            return httpx.Response(status, json=payload)

        def client(**kwargs: Any) -> httpx.Client:
            assert kwargs["follow_redirects"] is False
            return original_client(transport=httpx.MockTransport(handler), **kwargs)

        monkeypatch.setattr(gitea.httpx, "Client", client)
        return calls

    return install


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://gitea.example.com/", "https://gitea.example.com"),
        ("https://gitea.example.com/api/v1", "https://gitea.example.com"),
        ("https://gitea.example.com/api/v1/", "https://gitea.example.com"),
        ("http://10.0.0.5:3000", "http://10.0.0.5:3000"),
    ],
)
def test_credentials_normalize_instance_url(url: str, expected: str) -> None:
    creds = validate_create_credentials("gitea", {**CREDS, "base_url": url})
    assert creds["base_url"] == expected
    assert creds["token"] == "gitea-test-token"
    assert creds["internal_token"]


@pytest.mark.parametrize(
    "url",
    [
        "https://gitea.example.com?token=secret",
        "https://gitea.example.com/#/login",
        "http://user:secret@gitea.example.com",
    ],
)
def test_credentials_reject_unsafe_urls(url: str) -> None:
    with pytest.raises((ValueError, OctopError)):
        validate_create_credentials("gitea", {**CREDS, "base_url": url})


@pytest.mark.parametrize("token", ["", "  ", "secret\nheader"])
def test_credentials_require_token(token: str) -> None:
    with pytest.raises(ValueError, match="Token"):
        validate_create_credentials("gitea", {**CREDS, "token": token})


def test_catalog_localizes_fields_and_marks_token_secret() -> None:
    entry = get_catalog_entry("gitea")
    assert entry is not None
    assert (entry.auth_kind, entry.category, entry.mcp_mode) == (
        "custom_fields",
        "professional",
        "gateway",
    )
    zh = catalog_entry_to_dict(entry, locale="zh")
    en = catalog_entry_to_dict(entry, locale="en")
    fields = {field["key"]: field for field in zh["credential_fields"]}
    assert fields["base_url"]["label"] == "实例地址"
    assert fields["base_url"]["required"] is True
    assert fields["token"]["secret"] is True
    assert fields["token"]["required"] is True
    assert en["description"].startswith("Self-hosted Git")


def test_get_me_sends_token_header(mock_http: Callable[..., list[httpx.Request]]) -> None:
    calls = mock_http({"login": "octop", "full_name": "Octop User"})
    result = json.loads(gitea.call_tool(CREDS, "get_me", {}))
    assert result == {
        "login": "octop",
        "full_name": "Octop User",
        "email": None,
        "is_admin": None,
        "html_url": None,
    }
    assert calls[0].url.path == "/api/v1/user"
    assert calls[0].headers["authorization"] == "token gitea-test-token"


def test_search_repositories_maps_rows(mock_http: Callable[..., list[httpx.Request]]) -> None:
    calls = mock_http(
        {
            "data": [{"full_name": "octop/docs", "stars_count": 3, "default_branch": "main"}],
            "ok": True,
        }
    )
    result = json.loads(
        gitea.call_tool(CREDS, "search_repositories", {"query": "docs", "limit": 5})
    )
    assert calls[0].url.path == "/api/v1/repos/search"
    assert dict(calls[0].url.params) == {"q": "docs", "page": "1", "limit": "5"}
    assert result["repositories"][0]["full_name"] == "octop/docs"
    assert result["repositories"][0]["stars"] == 3


def test_list_issues_filters_type_and_state(
    mock_http: Callable[..., list[httpx.Request]],
) -> None:
    calls = mock_http(
        [
            {
                "number": 7,
                "title": "Fix login",
                "state": "open",
                "user": {"login": "cocoyu"},
                "labels": [{"name": "bug"}],
                "body": "steps" * 900,
                "comments": 2,
            }
        ]
    )
    result = json.loads(
        gitea.call_tool(CREDS, "list_issues", {"owner": "octop", "repo": "docs", "kind": "issues"})
    )
    assert calls[0].url.path == "/api/v1/repos/octop/docs/issues"
    assert dict(calls[0].url.params)["type"] == "issues"
    issue = result["issues"][0]
    assert issue["number"] == 7
    assert issue["user"] == "cocoyu"
    assert issue["labels"] == ["bug"]
    assert issue["is_pull_request"] is False
    assert len(issue["body"]) == 1200


def test_add_issue_comment_posts_body(mock_http: Callable[..., list[httpx.Request]]) -> None:
    calls = mock_http({"id": 11, "user": {"login": "octop"}, "body": "triaged"})
    result = json.loads(
        gitea.call_tool(
            CREDS,
            "add_issue_comment",
            {"owner": "octop", "repo": "docs", "index": 7, "body": "triaged"},
        )
    )
    assert calls[0].method == "POST"
    assert calls[0].url.path == "/api/v1/repos/octop/docs/issues/7/comments"
    assert json.loads(calls[0].content) == {"body": "triaged"}
    assert result["created"] is True
    assert result["comment"]["user"] == "octop"


def test_get_pull_request_reports_refs(mock_http: Callable[..., list[httpx.Request]]) -> None:
    mock_http(
        {
            "number": 9,
            "title": "Add gitea connector",
            "state": "open",
            "user": {"login": "octop"},
            "pull_request": {"merged": False},
            "head": {"ref": "feat/gitea", "repo": {"full_name": "octop/Octop"}},
            "base": {"ref": "main", "repo": {"full_name": "tencent/Octop"}},
        }
    )
    result = json.loads(
        gitea.call_tool(CREDS, "get_pull_request", {"owner": "octop", "repo": "Octop", "index": 9})
    )
    assert result["is_pull_request"] is True
    assert result["merged"] is False
    assert result["head_ref"] == "octop/Octop@feat/gitea"
    assert result["base_ref"] == "tencent/Octop@main"


def test_read_file_decodes_base64_and_truncates(
    mock_http: Callable[..., list[httpx.Request]],
) -> None:
    content = "# handbook\n" + "line\n" * 4000
    calls = mock_http(
        {
            "path": "docs/handbook.md",
            "type": "file",
            "size": len(content),
            "sha": "abc",
            "encoding": "base64",
            "content": base64.b64encode(content.encode()).decode(),
        }
    )
    result = json.loads(
        gitea.call_tool(
            CREDS,
            "read_file",
            {"owner": "octop", "repo": "docs", "filepath": "docs/handbook.md", "ref": "main"},
        )
    )
    assert calls[0].url.path == "/api/v1/repos/octop/docs/contents/docs/handbook.md"
    assert dict(calls[0].url.params) == {"ref": "main"}
    assert result["type"] == "file"
    assert result["truncated"] is True
    assert len(result["content"]) == 8000


def test_read_file_lists_directories(mock_http: Callable[..., list[httpx.Request]]) -> None:
    calls = mock_http(
        [{"name": "setup.md", "type": "file", "size": 12}, {"name": "img", "type": "dir"}]
    )
    result = json.loads(
        gitea.call_tool(CREDS, "read_file", {"owner": "octop", "repo": "docs", "filepath": "docs"})
    )
    assert calls[0].url.path == "/api/v1/repos/octop/docs/contents/docs"
    assert result["type"] == "dir"
    assert [entry["name"] for entry in result["entries"]] == ["setup.md", "img"]


def test_read_file_allows_dotfiles(mock_http: Callable[..., list[httpx.Request]]) -> None:
    calls = mock_http(
        {
            "type": "file",
            "size": 10,
            "sha": "def",
            "encoding": "base64",
            "content": base64.b64encode(b"*.pyc\n").decode(),
        }
    )
    result = json.loads(
        gitea.call_tool(
            CREDS,
            "read_file",
            {"owner": "octop", "repo": "docs", "filepath": ".github/workflows/ci.yml"},
        )
    )
    assert calls[0].url.path == "/api/v1/repos/octop/docs/contents/.github/workflows/ci.yml"
    assert result["content"] == "*.pyc\n"


@pytest.mark.parametrize(
    "args",
    [
        {"owner": "../evil", "repo": "docs", "index": 1},
        {"owner": "octop", "repo": "docs/../../x", "index": 1},
        {"owner": "octop", "repo": "docs", "index": "abc"},
        {"owner": "octop", "repo": "docs", "filepath": "a/../b", "ref": ""},
        {"owner": "octop", "repo": "docs", "filepath": "./README.md"},
        {"owner": "octop", "repo": "docs", "filepath": "."},
    ],
)
def test_tool_args_reject_path_injection(args: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        tool = "read_file" if "filepath" in args else "get_issue"
        gitea.call_tool(CREDS, tool, args)


@pytest.mark.parametrize("status", [401, 403, 404, 500])
def test_probe_fails_on_http_errors(
    status: int, mock_http: Callable[..., list[httpx.Request]]
) -> None:
    calls = mock_http({"message": "token is invalid"}, status=status)
    with pytest.raises(ValueError, match=f"HTTP {status}"):
        gitea.probe_credentials(CREDS)
    assert len(calls) == 1


def test_probe_localizes_error_to_zh(mock_http: Callable[..., list[httpx.Request]]) -> None:
    mock_http({"message": "unauthorized"}, status=401)
    with pytest.raises(ValueError, match="Gitea 请求失败：HTTP 401"):
        gitea.probe_credentials({**CREDS, "_locale": "zh"})


def test_probe_error_message_hides_token(mock_http: Callable[..., list[httpx.Request]]) -> None:
    mock_http({"message": "bad token gitea-test-token"}, status=401)
    with pytest.raises(ValueError) as exc:
        gitea.probe_credentials(CREDS)
    assert "gitea-test-token" not in str(exc.value)
    assert "***" in str(exc.value)


def test_probe_rejects_non_json(mock_http: Callable[..., list[httpx.Request]]) -> None:
    mock_http(text="<html>sign in</html>")
    with pytest.raises(ValueError, match="invalid API response"):
        gitea.probe_credentials(CREDS)


def test_probe_rejects_redirects(mock_http: Callable[..., list[httpx.Request]]) -> None:
    calls = mock_http(None, status=302)
    with pytest.raises(ValueError, match="HTTP 302"):
        gitea.probe_credentials(CREDS)
    assert len(calls) == 1


async def test_gateway_probe_and_tools_flow(mock_http: Callable[..., list[httpx.Request]]) -> None:
    entry = get_catalog_entry("gitea")
    assert entry is not None
    mock_http({"message": "unauthorized"}, status=401)
    failed = await probe_connector(entry, CREDS, instance_id="probe", config=OctopConfig())
    assert failed["ok"] is False
    mock_http({"login": "octop"})
    success = await probe_connector(entry, CREDS, instance_id="probe", config=OctopConfig())
    assert success["ok"] is True
    assert len(success["tools"]) == len(gitea.TOOLS)


def test_gateway_mcp_routes_calls(mock_http: Callable[..., list[httpx.Request]]) -> None:
    mock_http({"login": "octop"})
    listed = handle_mcp_request(
        kind="gitea", creds=CREDS, body={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    )
    assert [tool["name"] for tool in listed["result"]["tools"]][:2] == [
        "get_me",
        "search_repositories",
    ]
    called = handle_mcp_request(
        kind="gitea",
        creds=CREDS,
        body={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "get_me", "arguments": {}},
        },
    )
    assert json.loads(called["result"]["content"][0]["text"])["login"] == "octop"
