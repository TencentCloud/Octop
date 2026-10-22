"""OpenDesign configuration, persistent conversation sessions and task tracking."""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from langchain_core.tools import StructuredTool, ToolException
from langchain_mcp_adapters.tools import convert_mcp_tool_to_langchain_tool
from langgraph.config import get_config
from mcp import ClientSession, types

if TYPE_CHECKING:
    from octop_harness import ManagedMCPClient

from octop.i18n import tr
from octop.infra.connectors.mcp_tool_cache import fingerprint_mcp_spec

_IDLE_SECONDS = 600
_TERMINAL = {"succeeded", "failed", "canceled", "cancelled"}
_PROJECT_TOOLS = {
    "get_artifact",
    "get_project",
    "get_file",
    "search_files",
    "list_files",
    "write_file",
    "create_artifact",
    "delete_file",
    "delete_project",
    "start_run",
}


def _new_client(spec: dict[str, Any]) -> ManagedMCPClient:
    from octop_harness import ManagedMCPClient

    return ManagedMCPClient(spec)


def _json_field(value: Any, expected: type[Any], field: str) -> Any:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise ValueError(tr("connector.open_design.invalid_json", "en", field=field)) from exc
    if not isinstance(value, expected):
        raise ValueError(tr("connector.open_design.invalid_json", "en", field=field))
    return value


def normalize_credentials(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate a launch configuration without executing commands."""
    command = str(raw.get("command") or "").strip()
    if not command or "\x00" in command:
        raise ValueError(tr("connector.open_design.command_required", "en"))
    args = _json_field(raw.get("args") or [], list, "args")
    env = _json_field(raw.get("env") or {}, dict, "env")
    if not all(isinstance(v, str) and "\x00" not in v for v in args):
        raise ValueError(tr("connector.open_design.invalid_json", "en", field="args"))
    if not all(
        isinstance(k, str)
        and k
        and "=" not in k
        and "\x00" not in k
        and isinstance(v, str)
        and "\x00" not in v
        for k, v in env.items()
    ):
        raise ValueError(tr("connector.open_design.invalid_json", "en", field="env"))
    return {"command": command, "args": args, "env": env}


def connection_spec(creds: dict[str, Any]) -> dict[str, Any]:
    return {"transport": "stdio", **normalize_credentials(creds)}


def result_payload(result: Any) -> dict[str, Any]:
    """Read both structured and text-only OpenDesign releases."""
    if isinstance(result.structuredContent, dict):
        return dict(result.structuredContent)
    for block in result.content:
        if getattr(block, "type", None) == "text":
            try:
                payload = json.loads(block.text)
            except ValueError:
                continue
            if isinstance(payload, dict):
                return payload
    return {}


async def probe_open_design(creds: dict[str, Any]) -> dict[str, Any]:
    """Check the protocol, daemon and runtime catalog without generating files."""
    locale = str(creds.get("_locale") or "en")
    try:
        async with asyncio.timeout(25), _new_client(connection_spec(creds)) as client:
            tools = await client.get_tools()
            names = {tool.name for tool in tools.tools}
            if not {"list_projects", "start_run", "get_run"} <= names:
                return {"ok": False, "error": tr("connector.open_design.incompatible", locale)}
            projects = await client.call_tool("list_projects", {})
            if projects.isError:
                return {
                    "ok": False,
                    "error": tr("connector.open_design.daemon_unavailable", locale),
                }
            agents = await client.call_tool("list_agents", {})
            payload = result_payload(agents)
            available = payload.get("agents") or []
            return {
                "ok": not agents.isError and bool(available),
                "error": tr("connector.open_design.runtime_required", locale)
                if agents.isError or not available
                else None,
                "tool_count": len(tools.tools),
                "tools": [
                    {"name": t.name, "description": t.description or ""} for t in tools.tools
                ],
            }
    except ImportError:
        return {"ok": False, "error": tr("connector.open_design.harness_required", locale)}
    except (Exception, BaseExceptionGroup):
        # Transport errors may contain secret environment or command arguments.
        return {"ok": False, "error": tr("connector.open_design.connection_failed", locale)}


class OpenDesignRuntime:
    """Host-owned session pool. Protocol-only resources live in octop-harness."""

    def __init__(self, service: Any, repos: Any) -> None:
        self._service = service
        self._repos = repos
        self._clients: dict[tuple[int, str, str, str, str], ManagedMCPClient] = {}
        self._locks: dict[tuple[int, str, str, str, str], asyncio.Lock] = {}
        self._timers: dict[tuple[int, str, str, str, str], asyncio.TimerHandle] = {}

    async def start(self) -> None:
        """No background work is needed until a tool is selected."""

    async def shutdown(self) -> None:
        await self.close()

    def replace_persistence(self, service: Any, repos: Any) -> None:
        """Follow the host's control-plane binding; active agents are reloaded by it."""
        self._service, self._repos = service, repos

    async def close(self, *, user_id: int | None = None, agent_id: str | None = None) -> None:
        for key in list(self._clients):
            if (user_id is None or key[0] == user_id) and (agent_id is None or key[2] == agent_id):
                await self._expire(key)

    async def _expire(self, key: tuple[int, str, str, str, str]) -> None:
        lock = self._locks.get(key)
        if lock is None:
            return
        async with lock:
            timer = self._timers.pop(key, None)
            if timer:
                timer.cancel()
            client = self._clients.pop(key, None)
            if client:
                await client.aclose()

    async def build_tools(self, *, user_id: int, instance: Any, agent_id: str) -> list[Any]:
        creds = await asyncio.to_thread(self._service.decrypt, instance.instance_id)
        async with asyncio.timeout(25), _new_client(connection_spec(creds)) as client:
            definitions = await client.get_tools()
        session = _ScopedSession(self, instance.instance_id, agent_id)
        tools: list[Any] = []
        for definition in definitions.tools:
            tool = convert_mcp_tool_to_langchain_tool(
                cast(ClientSession, session),
                definition,
                server_name=instance.mcp_server_name,
                tool_name_prefix=True,
            )
            tool.description += "\n" + tr("connector.open_design.flow", "en")
            tools.append(tool)

        for name, schema in {
            "list_resources": {"type": "object", "properties": {"cursor": {"type": "string"}}},
            "read_resource": {
                "type": "object",
                "properties": {"uri": {"type": "string"}},
                "required": ["uri"],
            },
            "task_status": {"type": "object", "properties": {"wait": {"type": "boolean"}}},
        }.items():

            async def invoke(_name: str = name, **args: Any) -> tuple[str, Any]:
                result = await session.invoke(_name, args)
                return result.model_dump_json(by_alias=True), result.model_dump(
                    mode="json", by_alias=True
                )

            tools.append(
                StructuredTool(
                    name=f"{instance.mcp_server_name}_{name}",
                    description=tr(f"connector.open_design.{name}", "en"),
                    args_schema=schema,
                    coroutine=invoke,
                    response_format="content_and_artifact",
                    handle_tool_error=True,
                )
            )
        return tools

    async def call(
        self, user_id: int, instance_id: str, agent_id: str, name: str, args: dict[str, Any]
    ) -> Any:
        configurable = get_config().get("configurable") or {}
        thread_id = str(configurable.get("thread_id") or "")
        locale = str(configurable.get("locale") or "en")
        if not thread_id or str(configurable.get("user") or "") != str(user_id):
            raise ToolException(tr("connector.open_design.context_required", locale))
        instances = await asyncio.to_thread(
            self._service.list_user_instances,
            user_id,
            active_only=True,
            with_credentials=True,
            include_shared=True,
        )
        if not any(i.instance_id == instance_id and i.kind == "open-design" for i in instances):
            raise ToolException(tr("connector.open_design.context_required", locale))
        row = await asyncio.to_thread(self._repos.agent_repo.get, agent_id)
        if row is None or row.user_id not in (None, user_id):
            raise ToolException(tr("connector.open_design.context_required", locale))
        creds = await asyncio.to_thread(self._service.decrypt, instance_id)
        spec = connection_spec(creds)
        key = (user_id, instance_id, agent_id, thread_id, fingerprint_mcp_spec(spec))
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            timer = self._timers.pop(key, None)
            if timer:
                timer.cancel()
            client = self._clients.get(key)
            if client is None:
                client = _new_client(spec)
                self._clients[key] = client
            task_key = f"open_design:task:{user_id}:{instance_id}:{agent_id}:{thread_id}"
            try:
                state = json.loads(
                    await asyncio.to_thread(self._repos.settings_repo.get, task_key) or "{}"
                )
                arguments = {k: v for k, v in args.items() if v is not None}
                wait_for_task = name == "task_status" and arguments.pop("wait", False) is True
                if name in _PROJECT_TOOLS and not arguments.get("project"):
                    if not state.get("project"):
                        raise ToolException(tr("connector.open_design.project_required", locale))
                    arguments["project"] = state["project"]
                if name == "task_status":
                    if not state.get("runId"):
                        raise ToolException(tr("connector.open_design.no_task", locale))
                    name, arguments = "get_run", {"runId": state["runId"]}
                if name == "start_run":
                    if state.get("status") not in _TERMINAL and state.get("requestId"):
                        previous = state.get("arguments") or {}
                        comparison = {**arguments, "requestId": state["requestId"]}
                        comparison.pop("resume", None)
                        original = {k: v for k, v in previous.items() if k != "resume"}
                        if original != comparison:
                            raise ToolException(tr("connector.open_design.task_running", locale))
                        arguments = {
                            **previous,
                            **({"resume": True} if arguments.get("resume") is True else {}),
                        }
                    else:
                        arguments["requestId"] = str(arguments.get("requestId") or uuid4())
                    state = {
                        "version": 1,
                        "project": arguments["project"],
                        "requestId": arguments["requestId"],
                        "arguments": arguments,
                        "status": "submitting",
                        "updated_at": int(time.time()),
                    }
                    await asyncio.to_thread(
                        self._repos.settings_repo.set, task_key, json.dumps(state)
                    )
                if name == "list_resources":
                    return await client.list_resources(arguments.get("cursor"))
                if name == "read_resource":
                    return await client.read_resource(str(arguments["uri"]))
                result = await client.call_tool(name, arguments)
                if wait_for_task and not result.isError:
                    try:
                        async with asyncio.timeout(60):
                            while result_payload(result).get("status") in {"queued", "running"}:
                                await asyncio.sleep(30)
                                result = await client.call_tool(name, arguments)
                                if result.isError:
                                    break
                    except TimeoutError:
                        pass  # Deliver the latest known status; generation continues.
                if name == "collect_brief" and result.structuredContent is not None:
                    # Conversational forms need model-visible questions; artifacts
                    # alone are not included in the model's tool-result content.
                    result = result.model_copy(
                        update={
                            "content": [
                                *result.content,
                                types.TextContent(
                                    type="text",
                                    text=json.dumps(result.structuredContent, ensure_ascii=False),
                                ),
                            ]
                        }
                    )
                if not result.isError:
                    payload = result_payload(result)
                    if name == "create_project":
                        project = payload.get("project") or payload
                        state["project"] = project.get("id") or project.get("projectId")
                    elif name == "start_run":
                        state.update(
                            runId=payload.get("runId"), status=payload.get("status") or "queued"
                        )
                    elif name in {"get_run", "cancel_run"} and arguments.get("runId") == state.get(
                        "runId"
                    ):
                        state["status"] = payload.get("status") or state.get("status")
                    state["updated_at"] = int(time.time())
                    await asyncio.to_thread(
                        self._repos.settings_repo.set, task_key, json.dumps(state)
                    )
                elif name == "start_run":
                    state["status"] = "failed"
                    await asyncio.to_thread(
                        self._repos.settings_repo.set, task_key, json.dumps(state)
                    )
                return result
            except ToolException:
                raise
            except (Exception, BaseExceptionGroup) as exc:
                self._clients.pop(key, None)
                await client.aclose()
                raise ToolException(tr("connector.open_design.connection_failed", locale)) from exc
            finally:
                if key in self._clients:
                    self._timers[key] = asyncio.get_running_loop().call_later(
                        _IDLE_SECONDS,
                        lambda: asyncio.create_task(self._expire(key)),
                    )


class _ScopedSession:
    def __init__(self, runtime: OpenDesignRuntime, instance_id: str, agent_id: str) -> None:
        self._runtime, self._instance_id, self._agent_id = runtime, instance_id, agent_id

    async def invoke(self, name: str, arguments: dict[str, Any]) -> Any:
        configurable = get_config().get("configurable") or {}
        try:
            user_id = int(configurable.get("user") or "")
        except (ValueError, TypeError) as exc:
            raise ToolException(tr("connector.open_design.context_required", "en")) from exc
        return await self._runtime.call(user_id, self._instance_id, self._agent_id, name, arguments)

    async def call_tool(self, name: str, arguments: dict[str, Any], **_kwargs: Any) -> Any:
        try:
            return await self.invoke(name, arguments)
        except ToolException as exc:
            return types.CallToolResult(
                isError=True, content=[types.TextContent(type="text", text=str(exc))]
            )
