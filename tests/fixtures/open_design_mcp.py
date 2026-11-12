"""Stateful OpenDesign protocol fake, without a model or daemon."""

from __future__ import annotations

import os
from typing import Any

from mcp import types
from mcp.server.fastmcp import FastMCP

server = FastMCP("open-design-test")
draft: dict[str, str] = {}
requests: dict[str, dict[str, Any]] = {}


@server.tool()
def list_projects() -> dict[str, Any]:
    """List projects without writing."""
    return {"projects": []}


@server.tool()
def list_agents() -> dict[str, Any]:
    """List configured generators."""
    return {"agents": [{"id": "fake", "available": True}]}


@server.tool()
def collect_brief(projectTitle: str) -> dict[str, Any]:
    """Save a process-local brief."""
    draft["title"] = projectTitle
    return {"briefDraftId": "draft", "nonce": "nonce", "questions": []}


@server.tool()
def confirm_brief(briefDraftId: str, nonce: str, answers: dict[str, Any]) -> dict[str, Any]:
    """Return the process-local draft and object answers."""
    return {"title": draft["title"], "answers": answers}


@server.tool()
def start_run(
    project: str, prompt: str, requestId: str, skills: list[str] | None = None
) -> dict[str, Any]:
    """Create one logical task per request identity."""
    requests.setdefault(
        requestId, {"runId": requestId, "status": "running", "project": project, "skills": skills}
    )
    return requests[requestId]


@server.tool()
def get_run(runId: str) -> dict[str, Any]:
    """Return a completed task."""
    return {"runId": runId, "status": "succeeded", "previewUrl": "https://example.invalid/design"}


@server.resource("od://design-systems/test/DESIGN.md")
def design() -> str:
    return "Use a blue accent."


if os.environ.get("STDIO_TEST_PAGINATE") == "1":

    async def paginated_tools(request: types.ListToolsRequest) -> types.ServerResult:
        tools = await server.list_tools()
        cursor = getattr(request.params, "cursor", None)
        return types.ServerResult(
            types.ListToolsResult(
                tools=tools[:3] if cursor is None else tools[3:],
                nextCursor="second" if cursor is None else None,
            )
        )

    server._mcp_server.request_handlers[types.ListToolsRequest] = paginated_tools


if __name__ == "__main__":
    server.run(transport="stdio")
