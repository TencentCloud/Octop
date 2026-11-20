"""Gitea self-hosted Git tools using the public REST API v1."""

from __future__ import annotations

import base64
import json
import re
from typing import Any

import httpx

from octop.i18n import tr
from octop.infra.connectors.builder import normalize_gitea_base_url

_MAX_RESULTS = 20
_BODY_CHARS = 1200
_FILE_CHARS = 8000
_PAGE_SIZE = {"type": "integer", "minimum": 1, "maximum": 50}
_PAGING = {
    "page": {"type": "integer", "minimum": 1, "description": "Page number; default 1"},
    "limit": {**_PAGE_SIZE, "description": "Items per page; default 20"},
}
_REPO_REF = {
    "owner": {"type": "string", "minLength": 1, "description": "Repository owner (user or org)"},
    "repo": {"type": "string", "minLength": 1, "description": "Repository name"},
}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_me",
        "description": "Show the authenticated Gitea user behind the configured token.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_repositories",
        "description": "Search repositories on the Gitea instance by keyword, with pagination.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "description": "Search keyword"},
                **_PAGING,
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_my_repositories",
        "description": "List repositories owned by or accessible to the authenticated user.",
        "inputSchema": {"type": "object", "properties": {**_PAGING}},
    },
    {
        "name": "get_repository",
        "description": "Get repository details (description, default branch, stars, permissions).",
        "inputSchema": {
            "type": "object",
            "properties": {**_REPO_REF},
            "required": ["owner", "repo"],
        },
    },
    {
        "name": "list_issues",
        "description": (
            "List issues (or pull requests) of a repository, newest first. "
            "Use state=open/closed/all and kind=issues/pulls to filter."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_REF,
                "state": {
                    "type": "string",
                    "enum": ["open", "closed", "all"],
                    "description": "Issue state; default open",
                },
                "kind": {
                    "type": "string",
                    "enum": ["issues", "pulls"],
                    "description": "List plain issues or pull requests; default issues",
                },
                **_PAGING,
            },
            "required": ["owner", "repo"],
        },
    },
    {
        "name": "get_issue",
        "description": "Get one issue (or pull request) with title, body, labels, and assignees.",
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_REF,
                "index": {"type": "integer", "minimum": 1, "description": "Issue number"},
            },
            "required": ["owner", "repo", "index"],
        },
    },
    {
        "name": "list_issue_comments",
        "description": "List the comment thread of one issue (or pull request).",
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_REF,
                "index": {"type": "integer", "minimum": 1, "description": "Issue number"},
                **_PAGING,
            },
            "required": ["owner", "repo", "index"],
        },
    },
    {
        "name": "add_issue_comment",
        "description": "Post a new comment on an issue or pull request (requires token write scope).",
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_REF,
                "index": {"type": "integer", "minimum": 1, "description": "Issue number"},
                "body": {"type": "string", "minLength": 1, "description": "Comment text"},
            },
            "required": ["owner", "repo", "index", "body"],
        },
    },
    {
        "name": "list_pull_requests",
        "description": "List pull requests of a repository. Use state=open/closed/all to filter.",
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_REF,
                "state": {
                    "type": "string",
                    "enum": ["open", "closed", "all"],
                    "description": "Pull request state; default open",
                },
                **_PAGING,
            },
            "required": ["owner", "repo"],
        },
    },
    {
        "name": "get_pull_request",
        "description": "Get one pull request with base/head refs, body, and merge status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_REF,
                "index": {"type": "integer", "minimum": 1, "description": "Pull request number"},
            },
            "required": ["owner", "repo", "index"],
        },
    },
    {
        "name": "read_file",
        "description": (
            "Read a file (or list a directory) from a repository at a given ref. "
            "Best for configs, docs, and small source files; huge files are rejected upstream."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_REF,
                "filepath": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Slash-separated path inside the repository",
                },
                "ref": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Branch, tag, or commit SHA; default the default branch",
                },
            },
            "required": ["owner", "repo", "filepath"],
        },
    },
]


def list_tools() -> list[dict[str, Any]]:
    return TOOLS


def _text(creds: dict[str, Any], key: str, **kwargs: object) -> str:
    return tr(f"gitea.{key}", str(creds.get("_locale") or "en"), **kwargs)


def _token(creds: dict[str, Any]) -> str:
    token = str(creds.get("token") or creds.get("api_key") or "").strip()
    if not token or any(char in token for char in "\r\n\x00"):
        raise ValueError(_text(creds, "token_required"))
    return token


def _slug(creds: dict[str, Any], args: dict[str, Any], key: str) -> str:
    value = str(args.get(key) or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value) or ".." in value:
        raise ValueError(_text(creds, "invalid_slug", field=key))
    return value


def _index(creds: dict[str, Any], args: dict[str, Any]) -> int:
    raw = args.get("index")
    if raw is None:
        raise ValueError(_text(creds, "invalid_index"))
    try:
        index = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(_text(creds, "invalid_index")) from exc
    if index < 1:
        raise ValueError(_text(creds, "invalid_index"))
    return index


def _filepath(creds: dict[str, Any], args: dict[str, Any]) -> str:
    value = str(args.get("filepath") or "").strip().strip("/")
    if not value:
        raise ValueError(_text(creds, "invalid_path"))
    for segment in value.split("/"):
        if (
            segment in {".", ".."}
            or ".." in segment
            or not re.fullmatch(r"[A-Za-z0-9._-]+", segment)
        ):
            raise ValueError(_text(creds, "invalid_path"))
    return value


def _ref(args: dict[str, Any]) -> str:
    # A ref travels in the query string, so it has no path-injection surface.
    return str(args.get("ref") or "").strip()


def _page(args: dict[str, Any]) -> tuple[int, int]:
    return max(1, int(args.get("page") or 1)), max(
        1, min(int(args.get("limit") or _MAX_RESULTS), 50)
    )


def _request(
    creds: dict[str, Any],
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> tuple[httpx.Response, Any]:
    base_url = normalize_gitea_base_url(str(creds.get("base_url") or ""))
    token = _token(creds)
    try:
        with httpx.Client(timeout=30.0, follow_redirects=False) as client:
            response = client.request(
                method,
                f"{base_url}/api/v1{path}",
                headers={
                    "Accept": "application/json",
                    "Authorization": f"token {token}",
                },
                params=params,
                json=body,
            )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        reason = str(_message(exc.response) or exc.response.status_code)
        raise ValueError(
            _text(
                creds,
                "http_error",
                status=exc.response.status_code,
                reason=reason.replace(token, "***")[:300],
            )
        ) from exc
    except httpx.HTTPError as exc:
        raise ValueError(_text(creds, "network_error")) from exc
    # Redirects must never forward the credential to another host.
    if response.is_redirect:
        raise ValueError(_text(creds, "http_error", status=response.status_code, reason="redirect"))
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError(_text(creds, "invalid_response")) from exc
    return response, payload


def _message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return ""
    if isinstance(payload, dict):
        return str(payload.get("message") or "")
    return ""


def _user(item: dict[str, Any]) -> Any:
    return (item.get("user") or {}).get("login") if isinstance(item.get("user"), dict) else None


def _repository(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "full_name": row.get("full_name"),
        "description": str(row.get("description") or "")[:_BODY_CHARS],
        "default_branch": row.get("default_branch"),
        "stars": row.get("stars_count"),
        "forks": row.get("forks_count"),
        "open_issues": row.get("open_issues_count"),
        "updated_at": row.get("updated_at"),
        "html_url": row.get("html_url"),
        "archived": row.get("archived"),
    }


def _issue(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": row.get("number"),
        "title": row.get("title"),
        "state": row.get("state"),
        "is_pull_request": isinstance(row.get("pull_request"), dict),
        "user": _user(row),
        "labels": [label.get("name") for label in row.get("labels") or []],
        "assignees": [user.get("login") for user in row.get("assignees") or []],
        "body": str(row.get("body") or "")[:_BODY_CHARS],
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "comments": row.get("comments"),
        "html_url": row.get("html_url"),
    }


def _comment(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "user": _user(row),
        "body": str(row.get("body") or "")[:_BODY_CHARS],
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _pull(row: dict[str, Any]) -> dict[str, Any]:
    out = _issue(row)
    pr = row.get("pull_request") or {}
    if isinstance(pr, dict):
        out["merged"] = pr.get("merged")
    for side in ("head", "base"):
        endpoint = row.get(side) or {}
        repo = endpoint.get("repo") or {}
        out[f"{side}_ref"] = (
            f"{repo.get('full_name')}@{endpoint.get('ref')}"
            if repo.get("full_name") and endpoint.get("ref")
            else None
        )
    return out


def _total(response: httpx.Response) -> str | None:
    total = response.headers.get("x-total-count")
    return total if total and total.isdigit() else None


def _get_me(creds: dict[str, Any]) -> dict[str, Any]:
    _, payload = _request(creds, "GET", "/user")
    if not isinstance(payload, dict):
        raise ValueError(_text(creds, "invalid_response"))
    return {
        "login": payload.get("login"),
        "full_name": payload.get("full_name"),
        "email": payload.get("email"),
        "is_admin": payload.get("is_admin"),
        "html_url": payload.get("html_url"),
    }


def _search_repositories(creds: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        raise ValueError(_text(creds, "query_required"))
    page, limit = _page(args)
    response, payload = _request(
        creds, "GET", "/repos/search", params={"q": query, "page": page, "limit": limit}
    )
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError(_text(creds, "invalid_response"))
    return {
        "query": query,
        "page": page,
        "total": _total(response),
        "repositories": [_repository(row) for row in rows[:limit] if isinstance(row, dict)],
    }


def _list_my_repositories(creds: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    page, limit = _page(args)
    response, payload = _request(creds, "GET", "/user/repos", params={"page": page, "limit": limit})
    if not isinstance(payload, list):
        raise ValueError(_text(creds, "invalid_response"))
    return {
        "page": page,
        "total": _total(response),
        "repositories": [_repository(row) for row in payload[:limit] if isinstance(row, dict)],
    }


def _get_repository(creds: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    owner, repo = _slug(creds, args, "owner"), _slug(creds, args, "repo")
    _, payload = _request(creds, "GET", f"/repos/{owner}/{repo}")
    if not isinstance(payload, dict):
        raise ValueError(_text(creds, "invalid_response"))
    return _repository(payload)


def _list_issues(creds: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    owner, repo = _slug(creds, args, "owner"), _slug(creds, args, "repo")
    state = str(args.get("state") or "open")
    kind = str(args.get("kind") or "issues")
    page, limit = _page(args)
    response, payload = _request(
        creds,
        "GET",
        f"/repos/{owner}/{repo}/issues",
        params={"state": state, "type": kind, "page": page, "limit": limit},
    )
    if not isinstance(payload, list):
        raise ValueError(_text(creds, "invalid_response"))
    return {
        "owner": owner,
        "repo": repo,
        "state": state,
        "kind": kind,
        "page": page,
        "total": _total(response),
        "issues": [_issue(row) for row in payload[:limit] if isinstance(row, dict)],
    }


def _get_issue(creds: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    owner, repo = _slug(creds, args, "owner"), _slug(creds, args, "repo")
    index = _index(creds, args)
    _, payload = _request(creds, "GET", f"/repos/{owner}/{repo}/issues/{index}")
    if not isinstance(payload, dict):
        raise ValueError(_text(creds, "invalid_response"))
    return _issue(payload)


def _list_issue_comments(creds: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    owner, repo = _slug(creds, args, "owner"), _slug(creds, args, "repo")
    index = _index(creds, args)
    page, limit = _page(args)
    response, payload = _request(
        creds,
        "GET",
        f"/repos/{owner}/{repo}/issues/{index}/comments",
        params={"page": page, "limit": limit},
    )
    if not isinstance(payload, list):
        raise ValueError(_text(creds, "invalid_response"))
    return {
        "owner": owner,
        "repo": repo,
        "index": index,
        "page": page,
        "total": _total(response),
        "comments": [_comment(row) for row in payload[:limit] if isinstance(row, dict)],
    }


def _add_issue_comment(creds: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    owner, repo = _slug(creds, args, "owner"), _slug(creds, args, "repo")
    index = _index(creds, args)
    body = str(args.get("body") or "").strip()
    if not body:
        raise ValueError(_text(creds, "body_required"))
    _, payload = _request(
        creds, "POST", f"/repos/{owner}/{repo}/issues/{index}/comments", body={"body": body}
    )
    if not isinstance(payload, dict):
        raise ValueError(_text(creds, "invalid_response"))
    return {"created": True, "comment": _comment(payload)}


def _list_pull_requests(creds: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    owner, repo = _slug(creds, args, "owner"), _slug(creds, args, "repo")
    state = str(args.get("state") or "open")
    page, limit = _page(args)
    response, payload = _request(
        creds,
        "GET",
        f"/repos/{owner}/{repo}/pulls",
        params={"state": state, "page": page, "limit": limit},
    )
    if not isinstance(payload, list):
        raise ValueError(_text(creds, "invalid_response"))
    return {
        "owner": owner,
        "repo": repo,
        "state": state,
        "page": page,
        "total": _total(response),
        "pull_requests": [_pull(row) for row in payload[:limit] if isinstance(row, dict)],
    }


def _get_pull_request(creds: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    owner, repo = _slug(creds, args, "owner"), _slug(creds, args, "repo")
    index = _index(creds, args)
    _, payload = _request(creds, "GET", f"/repos/{owner}/{repo}/pulls/{index}")
    if not isinstance(payload, dict):
        raise ValueError(_text(creds, "invalid_response"))
    return _pull(payload)


def _read_file(creds: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    owner, repo = _slug(creds, args, "owner"), _slug(creds, args, "repo")
    filepath = _filepath(creds, args)
    params: dict[str, Any] = {}
    ref = _ref(args)
    if ref:
        params["ref"] = ref
    _, payload = _request(creds, "GET", f"/repos/{owner}/{repo}/contents/{filepath}", params=params)
    if isinstance(payload, list):
        return {
            "owner": owner,
            "repo": repo,
            "path": filepath,
            "type": "dir",
            "entries": [
                {"name": row.get("name"), "type": row.get("type"), "size": row.get("size")}
                for row in payload
                if isinstance(row, dict)
            ],
        }
    if not isinstance(payload, dict):
        raise ValueError(_text(creds, "invalid_response"))
    content = ""
    if payload.get("type") != "dir":
        try:
            content = base64.b64decode(str(payload.get("content") or "")).decode(
                "utf-8", errors="replace"
            )
        except (ValueError, TypeError) as exc:
            raise ValueError(_text(creds, "invalid_response")) from exc
    return {
        "owner": owner,
        "repo": repo,
        "path": payload.get("path") or filepath,
        "type": payload.get("type") or "file",
        "size": payload.get("size"),
        "sha": payload.get("sha"),
        "content": content[:_FILE_CHARS],
        "truncated": len(content) > _FILE_CHARS,
    }


def call_tool(creds: dict[str, Any], name: str, args: dict[str, Any]) -> str:
    if name == "get_me":
        result = _get_me(creds)
    elif name == "search_repositories":
        result = _search_repositories(creds, args)
    elif name == "list_my_repositories":
        result = _list_my_repositories(creds, args)
    elif name == "get_repository":
        result = _get_repository(creds, args)
    elif name == "list_issues":
        result = _list_issues(creds, args)
    elif name == "get_issue":
        result = _get_issue(creds, args)
    elif name == "list_issue_comments":
        result = _list_issue_comments(creds, args)
    elif name == "add_issue_comment":
        result = _add_issue_comment(creds, args)
    elif name == "list_pull_requests":
        result = _list_pull_requests(creds, args)
    elif name == "get_pull_request":
        result = _get_pull_request(creds, args)
    elif name == "read_file":
        result = _read_file(creds, args)
    else:
        raise ValueError(_text(creds, "unknown_tool", name=name))
    return json.dumps(result, ensure_ascii=False)


def probe_credentials(creds: dict[str, Any]) -> None:
    _get_me(creds)
