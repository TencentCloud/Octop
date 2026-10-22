"""Authorized discovery, material selection and project source operations."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

from octop.infra.connectors.open_design import (
    _new_client,
    connection_spec,
    normalize_credentials,
    result_payload,
)
from octop.infra.errors import ErrorCode, OctopError


class OpenDesignConsole:
    def __init__(self, runtime: Any, service: Any, repos: Any) -> None:
        self.runtime, self.service, self.repos = runtime, service, repos

    async def instance(self, user_id: int, instance_id: str) -> Any:
        visible = await asyncio.to_thread(
            self.service.list_user_instances,
            user_id,
            active_only=True,
            with_credentials=True,
            include_shared=True,
        )
        for instance in visible:
            if instance.instance_id == instance_id and instance.kind == "open-design":
                return instance
        raise OctopError.localized(ErrorCode.CONNECTOR_NOT_FOUND)

    async def scope(self, user_id: int, instance_id: str, agent_id: str, thread_id: str) -> None:
        if agent_id and thread_id:
            await self.runtime.tasks.list_authorized(user_id, agent_id, thread_id)
        await self.instance(user_id, instance_id)

    @asynccontextmanager
    async def client(self, user_id: int, instance_id: str) -> AsyncIterator[Any]:
        await self.instance(user_id, instance_id)
        creds = await asyncio.to_thread(self.service.decrypt, instance_id)
        try:
            async with asyncio.timeout(25), _new_client(connection_spec(creds)) as client:
                yield client
        except OctopError:
            raise
        except (Exception, BaseExceptionGroup) as exc:
            raise OctopError.localized(ErrorCode.CONNECTOR_MCP_LOAD_FAILED) from exc

    @staticmethod
    async def tool(client: Any, name: str, args: dict[str, Any]) -> Any:
        result = await client.call_tool(name, args)
        if result.isError:
            raise OctopError.localized(ErrorCode.CONNECTOR_MCP_LOAD_FAILED)
        return result

    async def health(self, user_id: int, instance_id: str) -> dict[str, Any]:
        await self.instance(user_id, instance_id)
        levels: list[dict[str, Any]] = []
        agents: list[dict[str, Any]] = []
        try:
            creds = await asyncio.to_thread(self.service.decrypt, instance_id)
            normalize_credentials(creds)
            levels.append({"level": "launch", "ok": True})
            async with self.client(user_id, instance_id) as client:
                tools = await client.get_tools()
                levels.append(
                    {
                        "level": "protocol",
                        "ok": {"start_run", "get_run", "list_projects"}
                        <= {t.name for t in tools.tools},
                        "count": len(tools.tools),
                    }
                )
                await self.tool(client, "list_projects", {})
                levels.append({"level": "daemon", "ok": True})
                payload = result_payload(await self.tool(client, "list_agents", {}))
                agents = payload.get("agents") or []
                levels.append({"level": "runtime", "ok": bool(agents), "count": len(agents)})
                try:
                    resources = await client.list_resources()
                    levels.append(
                        {"level": "resources", "ok": True, "count": len(resources.resources)}
                    )
                except Exception:
                    levels.append({"level": "resources", "ok": False})
        except (ValueError, OctopError):
            pass
        return {"levels": levels, "agents": agents, "generation_verified": False}

    @staticmethod
    def selection_key(user_id: int, instance_id: str, agent_id: str, thread_id: str) -> str:
        if not agent_id and not thread_id:
            return f"open_design:defaults:{user_id}:{instance_id}"
        return f"open_design:selection:{user_id}:{instance_id}:{agent_id}:{thread_id}"

    async def catalog(
        self,
        user_id: int,
        instance_id: str,
        agent_id: str,
        thread_id: str,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        await self.scope(user_id, instance_id, agent_id, thread_id)
        async with self.client(user_id, instance_id) as client:
            resources = await client.list_resources(cursor)
            agents = result_payload(await self.tool(client, "list_agents", {})).get("agents") or []

        raw = await asyncio.to_thread(
            self.repos.settings_repo.get,
            self.selection_key(user_id, instance_id, agent_id, thread_id),
        )
        if raw is None and agent_id and thread_id:
            raw = await asyncio.to_thread(
                self.repos.settings_repo.get, self.selection_key(user_id, instance_id, "", "")
            )
        return {
            "resources": [r.model_dump(mode="json", by_alias=True) for r in resources.resources],
            "next_cursor": resources.nextCursor,
            "agents": agents,
            "selection": json.loads(raw or "{}"),
        }

    @staticmethod
    async def validate_selection(client: Any, selection: dict[str, Any]) -> None:
        if selection.get("agent"):
            agents = (
                result_payload(await OpenDesignConsole.tool(client, "list_agents", {})).get(
                    "agents"
                )
                or []
            )
            selected = next((a for a in agents if a.get("id") == selection["agent"]), None)
            if selected is None:
                raise OctopError.localized(ErrorCode.OPEN_DESIGN_SELECTION_INVALID)
            models = {
                str(m.get("id")) if isinstance(m, dict) else str(m)
                for m in selected.get("models", [])
            }
            if selection.get("model") and selection["model"] not in models:
                raise OctopError.localized(ErrorCode.OPEN_DESIGN_SELECTION_INVALID)
        elif selection.get("model"):
            raise OctopError.localized(ErrorCode.OPEN_DESIGN_SELECTION_INVALID)
        if selection.get("skills") or selection.get("designSystem"):
            resources: set[str] = set()
            cursor = None
            for _ in range(30):
                page = await client.list_resources(cursor)
                resources.update(str(r.uri) for r in page.resources)
                cursor = page.nextCursor
                if not cursor:
                    break
            known = {
                (urlparse(uri).netloc, unquote(urlparse(uri).path.split("/")[1]))
                for uri in resources
                if len(urlparse(uri).path.split("/")) > 1
            }
            if any(("skills", skill) not in known for skill in selection.get("skills", [])) or (
                selection.get("designSystem")
                and ("design-systems", selection["designSystem"]) not in known
            ):
                raise OctopError.localized(ErrorCode.OPEN_DESIGN_SELECTION_INVALID)

    async def save_selection(
        self,
        user_id: int,
        instance_id: str,
        agent_id: str,
        thread_id: str,
        selection: dict[str, Any],
    ) -> None:
        await self.scope(user_id, instance_id, agent_id, thread_id)
        async with self.client(user_id, instance_id) as client:
            await self.validate_selection(client, selection)
        await asyncio.to_thread(
            self.repos.settings_repo.set,
            self.selection_key(user_id, instance_id, agent_id, thread_id),
            json.dumps(selection),
        )

    async def apply_selection(
        self,
        client: Any,
        user_id: int,
        instance_id: str,
        agent_id: str,
        thread_id: str,
        name: str,
        arguments: dict[str, Any],
    ) -> None:
        raw = await asyncio.to_thread(
            self.repos.settings_repo.get,
            self.selection_key(user_id, instance_id, agent_id, thread_id),
        )
        if raw is None:
            raw = await asyncio.to_thread(
                self.repos.settings_repo.get, self.selection_key(user_id, instance_id, "", "")
            )
        selection = json.loads(raw or "{}")
        if not selection:
            return
        await self.validate_selection(client, selection)
        if name == "create_project":
            if selection.get("designSystem"):
                arguments["designSystem"] = selection["designSystem"]
            if selection.get("skills"):
                arguments["skill"] = selection["skills"][0]
        elif name == "start_run":
            for key in ("agent", "model"):
                if selection.get(key):
                    arguments[key] = selection[key]
            if selection.get("skills"):
                arguments["skills"] = list(
                    dict.fromkeys([*selection["skills"], *arguments.get("skills", [])])
                )

    async def cancel(self, user_id: int, agent_id: str, thread_id: str, task_id: str) -> None:
        rows = await self.runtime.tasks.list_authorized(user_id, agent_id, thread_id)
        row = next((r for r in rows if r["task_id"] == task_id), None)
        if row is None or not row["run_id"]:
            raise OctopError.localized(ErrorCode.NOT_FOUND)
        if row["status"] in {"succeeded", "failed", "canceled", "cancelled"}:
            return
        async with self.client(user_id, row["instance_id"]) as client:
            await self.tool(client, "cancel_run", {"runId": row["run_id"]})
        await self.runtime.tasks.refresh_authorized(user_id, agent_id, thread_id, task_id)

    async def resource(
        self, user_id: int, instance_id: str, agent_id: str, thread_id: str, uri: str
    ) -> dict[str, Any]:
        await self.scope(user_id, instance_id, agent_id, thread_id)
        async with self.client(user_id, instance_id) as client:
            # The MCP server owns URI validation and only reads its own resources.
            result = await client.read_resource(uri)
        text = "\n".join(getattr(c, "text", "") for c in result.contents)
        return {"uri": uri, "text": text[:100_000], "truncated": len(text) > 100_000}

    @staticmethod
    def file_path(path: str) -> str:
        value = PurePosixPath(path)
        if (
            not path
            or str(value) == "."
            or value.is_absolute()
            or ".." in value.parts
            or "\\" in path
            or ":" in path
            or "\x00" in path
        ):
            raise OctopError.localized(ErrorCode.OPEN_DESIGN_PATH_INVALID)
        return str(value)

    async def project_scope(
        self, user_id: int, instance_id: str, agent_id: str, thread_id: str, project: str
    ) -> None:
        await self.scope(user_id, instance_id, agent_id, thread_id)
        rows = await self.runtime.tasks.list_authorized(user_id, agent_id, thread_id)
        if not any(r["instance_id"] == instance_id and r["project"] == project for r in rows):
            raise OctopError.localized(ErrorCode.NOT_FOUND)

    async def search(
        self,
        user_id: int,
        instance_id: str,
        agent_id: str,
        thread_id: str,
        project: str,
        query: str,
    ) -> dict[str, Any]:
        await self.project_scope(user_id, instance_id, agent_id, thread_id, project)
        async with self.client(user_id, instance_id) as client:
            return result_payload(
                await self.tool(
                    client, "search_files", {"project": project, "query": query, "max": 30}
                )
            )

    @staticmethod
    async def _file(client: Any, project: str, path: str) -> dict[str, Any]:
        result = await OpenDesignConsole.tool(
            client, "get_file", {"project": project, "path": path, "limit": 2001}
        )
        blocks = [b.text for b in result.content if getattr(b, "type", None) == "text"]
        content = blocks[-1] if blocks else ""
        truncated = (
            any(b.startswith("[od:file-window ") for b in blocks[:-1]) or len(content) > 512_000
        )
        return {
            "path": path,
            "content": content[:512_000],
            "digest": hashlib.sha256(content.encode()).hexdigest(),
            "truncated": truncated,
        }

    async def file(
        self, user_id: int, instance_id: str, agent_id: str, thread_id: str, project: str, path: str
    ) -> dict[str, Any]:
        await self.project_scope(user_id, instance_id, agent_id, thread_id, project)
        async with self.client(user_id, instance_id) as client:
            return await self._file(client, project, self.file_path(path))

    async def edit(
        self,
        user_id: int,
        instance_id: str,
        agent_id: str,
        thread_id: str,
        project: str,
        path: str,
        digest: str,
        content: str,
        locale: str,
    ) -> dict[str, Any]:
        await self.project_scope(user_id, instance_id, agent_id, thread_id, project)
        path = self.file_path(path)
        rows = await asyncio.to_thread(
            self.repos.open_design_task_repo.active_project, user_id, instance_id, project
        )
        if rows:
            raise OctopError.localized(ErrorCode.OPEN_DESIGN_TASK_RUNNING, locale)
        async with self.client(user_id, instance_id) as client:
            current = await self._file(client, project, path)
            if current["truncated"] or current["digest"] != digest:
                raise OctopError.localized(ErrorCode.OPEN_DESIGN_FILE_CONFLICT, locale)
            await self.tool(
                client, "write_file", {"project": project, "path": path, "content": content}
            )
            verified = await self._file(client, project, path)
            if verified["content"] != content or verified["truncated"]:
                raise OctopError.localized(ErrorCode.CONNECTOR_MCP_LOAD_FAILED, locale)
            metadata = result_payload(await self.tool(client, "get_project", {"project": project}))
        return {**verified, "previewUrl": metadata.get("previewUrl")}
