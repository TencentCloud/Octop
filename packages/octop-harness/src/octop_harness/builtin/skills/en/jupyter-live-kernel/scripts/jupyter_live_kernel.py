#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "jupyter-client>=8",
#     "jupyter-server>=2",
#     "nbformat>=5",
#     "requests>=2",
#     "websocket-client>=1.8",
# ]
# ///
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode, urljoin, urlparse, urlunparse

import requests
import websocket
from jupyter_client import BlockingKernelClient
from jupyter_client.connect import find_connection_file
from jupyter_server.serverapp import list_running_servers
from nbformat import v4 as nbf

from octop_harness.backends.utils import DEFENSIVE_OP_ERRORS

DEFAULT_TIMEOUT = 10.0
DEFAULT_EXEC_TIMEOUT = 30.0


class CommandError(RuntimeError):
    """Raised when the CLI cannot satisfy a request."""


class HTTPCommandError(CommandError):
    """Raised when an HTTP request completes but returns an error."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class TransportRetryUnsafeError(CommandError):
    """Raised when retrying execution could duplicate side effects."""

    def __init__(self, message: str, *, request_sent: bool) -> None:
        super().__init__(message)
        self.request_sent = request_sent


@dataclass
class ServerInfo:
    url: str
    base_url: str
    root_dir: str
    token: str
    pid: int | None = None
    port: int | None = None
    version: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def root_url(self) -> str:
        base = (self.base_url or "/").strip("/")
        suffix = f"{base}/" if base else ""
        return urljoin(self.url if self.url.endswith("/") else f"{self.url}/", suffix)

    @property
    def ws_root_url(self) -> str:
        parts = urlparse(self.root_url)
        scheme = "wss" if parts.scheme == "https" else "ws"
        return urlunparse((scheme, parts.netloc, parts.path, "", "", ""))

    def summary(self) -> dict[str, Any]:
        return {
            "url": self.root_url,
            "port": self.port,
            "pid": self.pid,
            "version": self.version,
            "root_dir": self.root_dir,
            "token_present": bool(self.token),
        }


@dataclass
class ProbeResult:
    reachable: bool
    auth_ok: bool
    error: str | None = None
    sessions_count: int | None = None
    lab_workspaces_available: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "reachable": self.reachable,
            "auth_ok": self.auth_ok,
            "error": self.error,
            "sessions_count": self.sessions_count,
            "lab_workspaces_available": self.lab_workspaces_available,
        }


@dataclass
class ExecutionResult:
    transport: str
    kernel_id: str
    session_id: str | None
    path: str | None
    reply: dict[str, Any]
    events: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "transport": self.transport,
            "kernel_id": self.kernel_id,
            "session_id": self.session_id,
            "path": self.path,
            "reply": self.reply,
            "events": self.events,
            "status": self.reply.get("status"),
        }


@dataclass
class KernelTarget:
    kernel_id: str
    kernel_name: str | None
    session_id: str | None
    path: str | None


@dataclass
class ExecuteRequest:
    code: str
    silent: bool = False
    store_history: bool = True
    user_expressions: dict[str, str] = field(default_factory=dict)
    stop_on_error: bool = True


class ServerClient:
    def __init__(self, server: ServerInfo, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.server = server
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        if self.server.token:
            self.session.headers["Authorization"] = f"token {self.server.token}"
        self._primed = False

    def _prime(self) -> None:
        if self._primed:
            return
        params = {"token": self.server.token} if self.server.token else None
        try:
            self.session.get(self.server.root_url, params=params, timeout=self.timeout)
        except requests.RequestException:
            self._primed = True
            return
        xsrf = self.session.cookies.get("_xsrf")
        if xsrf:
            self.session.headers["X-XSRFToken"] = xsrf
        self._primed = True

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        timeout: float | None = None,
        expect_json: bool = True,
    ) -> Any:
        self._prime()
        merged_params = dict(params or {})
        if self.server.token and "token" not in merged_params:
            merged_params["token"] = self.server.token
        url = urljoin(self.server.root_url, path.lstrip("/"))
        response = self.session.request(
            method,
            url,
            params=merged_params,
            json=payload,
            timeout=timeout or self.timeout,
        )
        if response.status_code >= 400:
            snippet = response.text[:400].strip()
            raise HTTPCommandError(
                f"{method} {url} failed with {response.status_code}: {snippet}",
                status_code=response.status_code,
            )
        if expect_json:
            return response.json()
        return response.text

    def websocket_headers(self) -> list[str]:
        self._prime()
        headers: list[str] = []
        if self.server.token:
            headers.append(f"Authorization: token {self.server.token}")
        cookies = self.session.cookies.get_dict()
        if cookies:
            headers.append("Cookie: " + "; ".join(f"{key}={value}" for key, value in cookies.items()))
        xsrf = cookies.get("_xsrf")
        if xsrf:
            headers.append(f"X-XSRFToken: {xsrf}")
        return headers


def _server_from_raw(raw: dict[str, Any]) -> ServerInfo:
    return ServerInfo(
        url=raw["url"],
        base_url=raw.get("base_url", "/"),
        root_dir=raw.get("root_dir") or raw.get("notebook_dir") or "",
        token=raw.get("token", ""),
        pid=raw.get("pid"),
        port=raw.get("port"),
        version=raw.get("version"),
        raw=raw,
    )


def _running_server_infos() -> list[ServerInfo]:
    return [_server_from_raw(raw) for raw in list_running_servers()]


def discover_servers(timeout: float = DEFAULT_TIMEOUT) -> list[dict[str, Any]]:
    discovered: list[dict[str, Any]] = []
    for server in _running_server_infos():
        probe = probe_server(server, timeout=timeout)
        discovered.append({"server": server.summary(), "probe": probe.as_dict()})
    discovered.sort(key=lambda item: (not item["probe"]["reachable"], item["server"]["url"]))
    return discovered


def probe_server(server: ServerInfo, timeout: float = DEFAULT_TIMEOUT) -> ProbeResult:
    client = ServerClient(server, timeout=timeout)
    try:
        sessions = client.request("GET", "api/sessions", timeout=timeout)
    except HTTPCommandError as exc:
        return ProbeResult(
            reachable=True,
            auth_ok=exc.status_code not in {401, 403},
            error=str(exc),
        )
    except requests.RequestException as exc:
        return ProbeResult(reachable=False, auth_ok=False, error=str(exc))

    lab_available = False
    try:
        client.request("GET", "lab/api/workspaces", timeout=timeout)
        lab_available = True
    except (CommandError, requests.RequestException):
        lab_available = False

    return ProbeResult(
        reachable=True,
        auth_ok=True,
        sessions_count=len(sessions) if isinstance(sessions, list) else None,
        lab_workspaces_available=lab_available,
    )


def _select_server(
    *,
    server_url: str | None,
    port: int | None,
    timeout: float,
) -> ServerInfo:
    if server_url or port:
        for server in _running_server_infos():
            if port and server.port != port:
                continue
            if server_url and server.root_url.rstrip("/") != server_url.rstrip("/"):
                continue
            probe = probe_server(server, timeout=timeout)
            if probe.reachable and probe.auth_ok:
                return server
            criterion = server_url or f"port {port}"
            if probe.reachable and not probe.auth_ok:
                raise CommandError(
                    f"Jupyter server matched {criterion}, but authentication failed. "
                    "Use a server with working auth or refresh the server token."
                )
        criterion = server_url or f"port {port}"
        raise CommandError(f"No reachable Jupyter server matched {criterion}.")

    reachable_raw: list[ServerInfo] = []
    for server in _running_server_infos():
        probe = probe_server(server, timeout=timeout)
        if probe.reachable and probe.auth_ok:
            reachable_raw.append(server)

    if not reachable_raw:
        raise CommandError("No reachable Jupyter servers with working auth were discovered.")
    if len(reachable_raw) > 1:
        urls = ", ".join(server.root_url for server in reachable_raw)
        raise CommandError(
            f"Multiple reachable Jupyter servers were discovered. Pass --server-url or --port. Candidates: {urls}"
        )
    return reachable_raw[0]


def list_sessions(server: ServerInfo, timeout: float = DEFAULT_TIMEOUT) -> list[dict[str, Any]]:
    client = ServerClient(server, timeout=timeout)
    sessions = client.request("GET", "api/sessions")
    result: list[dict[str, Any]] = []
    for session in sessions:
        kernel = session.get("kernel") or {}
        result.append(
            {
                "id": session.get("id"),
                "path": session.get("path"),
                "type": session.get("type"),
                "name": session.get("name"),
                "kernel": {
                    "id": kernel.get("id"),
                    "name": kernel.get("name"),
                    "execution_state": kernel.get("execution_state"),
                    "last_activity": kernel.get("last_activity"),
                    "connections": kernel.get("connections"),
                },
            }
        )
    return result


def _extract_notebook_paths(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for child in value.values():
            found.update(_extract_notebook_paths(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_extract_notebook_paths(child))
    elif isinstance(value, str) and value.startswith("notebook:"):
        found.add(value.split(":", 1)[1])
    return found


def _path_exists_in_server_root(
    server: ServerInfo,
    path: str,
    *,
    client: ServerClient | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> bool:
    if server.root_dir and os.path.isdir(server.root_dir):
        return (Path(server.root_dir) / path).exists()

    client = client or ServerClient(server, timeout=timeout)
    try:
        encoded_path = quote(path, safe="/")
        client.request(
            "GET",
            f"api/contents/{encoded_path}",
            params={"content": 0},
            timeout=timeout,
        )
        return True
    except (CommandError, requests.RequestException):
        return False


def list_workspaces(server: ServerInfo, timeout: float = DEFAULT_TIMEOUT) -> list[dict[str, Any]]:
    client = ServerClient(server, timeout=timeout)
    try:
        payload = client.request("GET", "lab/api/workspaces")
    except HTTPCommandError as exc:
        if exc.status_code == 404:
            return []
        raise

    values = payload.get("workspaces", {}).get("values", [])
    result: list[dict[str, Any]] = []
    for workspace in values:
        data = workspace.get("data", {})
        notebooks = sorted(
            path
            for path in _extract_notebook_paths(data.get("layout-restorer:data", data))
            if _path_exists_in_server_root(server, path, client=client, timeout=timeout)
        )
        if notebooks:
            result.append(
                {
                    "id": workspace.get("metadata", {}).get("id"),
                    "notebooks": notebooks,
                    "raw": workspace,
                }
            )
    return result


def combined_open_notebooks(server: ServerInfo, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    sessions = [item for item in list_sessions(server, timeout=timeout) if item.get("type") == "notebook"]
    workspaces = list_workspaces(server, timeout=timeout)
    combined: dict[str, dict[str, Any]] = {}

    for session in sessions:
        path = session.get("path")
        if not path:
            continue
        item = combined.setdefault(
            path,
            {"path": path, "live": False, "session_ids": [], "kernel_ids": [], "workspace_ids": []},
        )
        item["live"] = True
        if session["id"]:
            item["session_ids"].append(session["id"])
        kernel_id = (session.get("kernel") or {}).get("id")
        if kernel_id:
            item["kernel_ids"].append(kernel_id)

    for workspace in workspaces:
        workspace_id = workspace.get("id")
        for path in workspace.get("notebooks", []):
            item = combined.setdefault(
                path,
                {"path": path, "live": False, "session_ids": [], "kernel_ids": [], "workspace_ids": []},
            )
            if workspace_id:
                item["workspace_ids"].append(workspace_id)

    open_notebooks = []
    for path in sorted(combined):
        item = combined[path]
        item["session_ids"] = sorted(set(item["session_ids"]))
        item["kernel_ids"] = sorted(set(item["kernel_ids"]))
        item["workspace_ids"] = sorted(set(item["workspace_ids"]))
        open_notebooks.append(item)

    return {
        "server": server.summary(),
        "sessions": sessions,
        "workspaces": [{"id": ws["id"], "notebooks": ws["notebooks"]} for ws in workspaces],
        "open_notebooks": open_notebooks,
    }


def get_contents(
    server: ServerInfo,
    path: str,
    *,
    include_outputs: bool,
    raw: bool,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    model = _load_notebook_model(server, path, timeout=timeout)
    if raw:
        return model

    content = model.get("content") or {}
    cells = []
    for index, cell in enumerate(content.get("cells", [])):
        cells.append(_summarize_cell(cell, index=index, include_outputs=include_outputs))

    return {
        "path": model.get("path"),
        "name": model.get("name"),
        "type": model.get("type"),
        "last_modified": model.get("last_modified"),
        "format": model.get("format"),
        "nbformat": content.get("nbformat"),
        "nbformat_minor": content.get("nbformat_minor"),
        "cells": cells,
    }


def _load_notebook_model(server: ServerInfo, path: str, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    client = ServerClient(server, timeout=timeout)
    encoded_path = quote(path, safe="/")
    model = client.request(
        "GET",
        f"api/contents/{encoded_path}",
        params={"content": 1, "type": "notebook"},
    )
    _normalize_notebook_content(model.setdefault("content", {}), notebook_path=path)
    return model


def _save_notebook_content(
    server: ServerInfo,
    path: str,
    content: dict[str, Any],
    timeout: float = DEFAULT_TIMEOUT,
    expected_last_modified: str | None = None,
) -> dict[str, Any]:
    client = ServerClient(server, timeout=timeout)
    encoded_path = quote(path, safe="/")
    _normalize_notebook_content(content, notebook_path=path)
    if expected_last_modified is not None:
        current = client.request(
            "GET",
            f"api/contents/{encoded_path}",
            params={"content": 0, "type": "notebook"},
        )
        if current.get("last_modified") != expected_last_modified:
            raise CommandError("Notebook changed since it was loaded; reload contents and retry the edit.")
    return client.request(
        "PUT",
        f"api/contents/{encoded_path}",
        payload={"type": "notebook", "format": "json", "content": content},
    )


def _synthetic_cell_id(cell: dict[str, Any], *, notebook_path: str, cell_index: int) -> str:
    payload = json.dumps(
        {
            "path": notebook_path,
            "index": cell_index,
            "cell_type": cell.get("cell_type"),
            "source": cell.get("source", ""),
            "metadata": cell.get("metadata", {}),
        },
        sort_keys=True,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"synthetic-{digest}"


def _ensure_cell_id(cell: dict[str, Any], *, notebook_path: str | None, cell_index: int) -> None:
    if cell.get("id"):
        return
    if notebook_path:
        cell["id"] = _synthetic_cell_id(cell, notebook_path=notebook_path, cell_index=cell_index)
        return
    cell["id"] = uuid.uuid4().hex


def _normalize_notebook_content(content: dict[str, Any], notebook_path: str | None = None) -> None:
    content.setdefault("metadata", {})
    content.setdefault("nbformat", 4)
    content.setdefault("nbformat_minor", 5)
    cells = content.setdefault("cells", [])
    for cell_index, cell in enumerate(cells):
        source = cell.get("source", "")
        if isinstance(source, list):
            cell["source"] = "".join(source)
        _ensure_cell_id(cell, notebook_path=notebook_path, cell_index=cell_index)


def _summarize_cell(
    cell: dict[str, Any],
    *,
    index: int,
    include_outputs: bool,
) -> dict[str, Any]:
    summary = {
        "index": index,
        "cell_id": cell.get("id"),
        "cell_type": cell.get("cell_type"),
        "source": cell.get("source", ""),
    }
    if "execution_count" in cell:
        summary["execution_count"] = cell.get("execution_count")
    if include_outputs and cell.get("cell_type") == "code":
        summary["outputs"] = [_summarize_output(output) for output in cell.get("outputs", [])]
    return summary


def _resolve_cell_index(
    cells: list[dict[str, Any]],
    *,
    index: int | None,
    cell_id: str | None,
) -> int:
    if index is not None:
        if index < 0 or index >= len(cells):
            raise CommandError(f"Cell index {index} is out of range for notebook with {len(cells)} cells.")
        return index
    if cell_id is not None:
        for current_index, cell in enumerate(cells):
            if cell.get("id") == cell_id:
                return current_index
        raise CommandError(f"No cell matched id {cell_id}.")
    raise CommandError("Pass one of --index or --cell-id.")


def _build_cell(cell_type: str, source: str) -> dict[str, Any]:
    if cell_type == "code":
        return dict(nbf.new_code_cell(source=source))
    if cell_type == "markdown":
        return dict(nbf.new_markdown_cell(source=source))
    if cell_type == "raw":
        return dict(nbf.new_raw_cell(source=source))
    raise CommandError(f"Unsupported cell type {cell_type!r}.")


def edit_cell_source(
    server: ServerInfo,
    *,
    path: str,
    index: int | None,
    cell_id: str | None,
    source: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    model = _load_notebook_model(server, path, timeout=timeout)
    cells = model["content"]["cells"]
    resolved_index = _resolve_cell_index(cells, index=index, cell_id=cell_id)
    if cells[resolved_index].get("source", "") == source:
        return {
            "path": path,
            "operation": "replace-source",
            "changed": False,
            "cell": _summarize_cell(cells[resolved_index], index=resolved_index, include_outputs=False),
            "cell_count": len(cells),
        }
    cells[resolved_index]["source"] = source
    _save_notebook_content(
        server,
        path,
        model["content"],
        timeout=timeout,
        expected_last_modified=model.get("last_modified"),
    )
    return {
        "path": path,
        "operation": "replace-source",
        "changed": True,
        "cell": _summarize_cell(cells[resolved_index], index=resolved_index, include_outputs=False),
        "cell_count": len(cells),
    }


def insert_cell(
    server: ServerInfo,
    *,
    path: str,
    cell_type: str,
    source: str,
    at_index: int,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    model = _load_notebook_model(server, path, timeout=timeout)
    cells = model["content"]["cells"]
    if at_index < 0 or at_index > len(cells):
        raise CommandError(f"Insert index {at_index} is out of range for notebook with {len(cells)} cells.")
    cell = _build_cell(cell_type, source)
    cells.insert(at_index, cell)
    _save_notebook_content(
        server,
        path,
        model["content"],
        timeout=timeout,
        expected_last_modified=model.get("last_modified"),
    )
    return {
        "path": path,
        "operation": "insert-cell",
        "changed": True,
        "cell": _summarize_cell(cell, index=at_index, include_outputs=False),
        "cell_count": len(cells),
    }


def delete_cell(
    server: ServerInfo,
    *,
    path: str,
    index: int | None,
    cell_id: str | None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    model = _load_notebook_model(server, path, timeout=timeout)
    cells = model["content"]["cells"]
    resolved_index = _resolve_cell_index(cells, index=index, cell_id=cell_id)
    removed = cells.pop(resolved_index)
    _save_notebook_content(
        server,
        path,
        model["content"],
        timeout=timeout,
        expected_last_modified=model.get("last_modified"),
    )
    return {
        "path": path,
        "operation": "delete-cell",
        "changed": True,
        "deleted_cell": _summarize_cell(removed, index=resolved_index, include_outputs=False),
        "cell_count": len(cells),
    }


def move_cell(
    server: ServerInfo,
    *,
    path: str,
    index: int | None,
    cell_id: str | None,
    to_index: int,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    model = _load_notebook_model(server, path, timeout=timeout)
    cells = model["content"]["cells"]
    resolved_index = _resolve_cell_index(cells, index=index, cell_id=cell_id)
    original_count = len(cells)
    if to_index < 0 or to_index >= original_count:
        raise CommandError(f"Target index {to_index} is out of range for notebook with {original_count} cells.")
    if resolved_index == to_index:
        return {
            "path": path,
            "operation": "move-cell",
            "changed": False,
            "from_index": resolved_index,
            "to_index": to_index,
            "cell": _summarize_cell(cells[resolved_index], index=resolved_index, include_outputs=False),
            "cell_count": len(cells),
        }
    cell = cells.pop(resolved_index)
    cells.insert(to_index, cell)
    _save_notebook_content(
        server,
        path,
        model["content"],
        timeout=timeout,
        expected_last_modified=model.get("last_modified"),
    )
    return {
        "path": path,
        "operation": "move-cell",
        "changed": True,
        "from_index": resolved_index,
        "to_index": to_index,
        "cell": _summarize_cell(cell, index=to_index, include_outputs=False),
        "cell_count": len(cells),
    }


def clear_cell_outputs(
    server: ServerInfo,
    *,
    path: str,
    index: int | None,
    cell_id: str | None,
    all_cells: bool,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    model = _load_notebook_model(server, path, timeout=timeout)
    cells = model["content"]["cells"]
    if all_cells or (index is None and cell_id is None):
        target_indexes = [cell_index for cell_index, cell in enumerate(cells) if cell.get("cell_type") == "code"]
    else:
        target_indexes = [_resolve_cell_index(cells, index=index, cell_id=cell_id)]

    changed = False
    cleared_cells: list[dict[str, Any]] = []
    for cell_index in target_indexes:
        cell = cells[cell_index]
        if cell.get("cell_type") != "code":
            continue
        outputs = cell.get("outputs") or []
        execution_count = cell.get("execution_count")
        if outputs or execution_count is not None:
            cell["outputs"] = []
            cell["execution_count"] = None
            changed = True
        cleared_cells.append(_summarize_cell(cell, index=cell_index, include_outputs=False))

    if changed:
        _save_notebook_content(
            server,
            path,
            model["content"],
            timeout=timeout,
            expected_last_modified=model.get("last_modified"),
        )

    return {
        "path": path,
        "operation": "clear-outputs",
        "changed": changed,
        "cleared_cell_count": len(cleared_cells),
        "cells": cleared_cells,
        "cell_count": len(cells),
    }


def _events_to_notebook_outputs(
    events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int | None]:
    """Convert execution events to notebook cell output format.

    Returns (outputs, execution_count).
    """
    outputs: list[dict[str, Any]] = []
    execution_count: int | None = None
    for event in events:
        etype = event.get("type")
        if etype == "execute_input":
            execution_count = event.get("execution_count")
        elif etype == "stream":
            outputs.append(
                {
                    "output_type": "stream",
                    "name": event.get("name", "stdout"),
                    "text": event.get("text", ""),
                }
            )
        elif etype == "execute_result":
            execution_count = event.get("execution_count") or execution_count
            outputs.append(
                {
                    "output_type": "execute_result",
                    "data": event.get("data", {}),
                    "metadata": event.get("metadata", {}),
                    "execution_count": event.get("execution_count"),
                }
            )
        elif etype == "display_data":
            outputs.append(
                {
                    "output_type": "display_data",
                    "data": event.get("data", {}),
                    "metadata": event.get("metadata", {}),
                }
            )
        elif etype == "error":
            outputs.append(
                {
                    "output_type": "error",
                    "ename": event.get("ename", ""),
                    "evalue": event.get("evalue", ""),
                    "traceback": event.get("traceback", []),
                }
            )
    return outputs, execution_count


def _save_run_all_outputs(
    server: ServerInfo,
    path: str,
    *,
    executed_model: dict[str, Any],
    timeout: float,
) -> None:
    """Merge executed outputs into the latest notebook model before saving.

    This keeps notebook-level metadata and concurrent non-source changes made by JupyterLab,
    while still rejecting structural or source edits that would invalidate the run results.
    """
    latest_model = _load_notebook_model(server, path, timeout=timeout)
    executed_cells = executed_model.get("cells") or []
    latest_cells = (latest_model.get("content") or {}).get("cells") or []

    if len(executed_cells) != len(latest_cells):
        raise CommandError(
            "Notebook changed while run-all was executing; cell structure no longer matches, so outputs were not saved."
        )

    for index, (executed_cell, latest_cell) in enumerate(zip(executed_cells, latest_cells, strict=False)):
        if executed_cell.get("cell_type") != latest_cell.get("cell_type"):
            raise CommandError(
                f"Notebook changed while run-all was executing; cell {index} changed type, so outputs were not saved."
            )
        if executed_cell.get("cell_type") != "code":
            continue
        executed_id = executed_cell.get("id")
        latest_id = latest_cell.get("id")
        if executed_id and latest_id and executed_id != latest_id:
            raise CommandError(
                "Notebook changed while run-all was executing; "
                f"cell {index} changed identity, so outputs were not saved."
            )
        if (executed_cell.get("source") or "") != (latest_cell.get("source") or ""):
            raise CommandError(
                "Notebook changed while run-all was executing; "
                f"code cell {index} changed source, so outputs were not saved."
            )
        latest_cell["outputs"] = executed_cell.get("outputs", [])
        latest_cell["execution_count"] = executed_cell.get("execution_count")

    _save_notebook_content(
        server,
        path,
        latest_model["content"],
        timeout=timeout,
        expected_last_modified=latest_model.get("last_modified"),
    )


def _summarize_output(output: dict[str, Any]) -> dict[str, Any]:
    output_type = output.get("output_type")
    if output_type == "stream":
        return {
            "output_type": "stream",
            "name": output.get("name"),
            "text": output.get("text", ""),
        }
    if output_type in {"display_data", "execute_result"}:
        return {
            "output_type": output_type,
            "data": output.get("data", {}),
            "execution_count": output.get("execution_count"),
        }
    if output_type == "error":
        return {
            "output_type": "error",
            "ename": output.get("ename"),
            "evalue": output.get("evalue"),
            "traceback": output.get("traceback", []),
        }
    return output


def _resolve_session(
    server: ServerInfo,
    *,
    path: str | None,
    session_id: str | None,
    kernel_id: str | None,
    timeout: float,
) -> dict[str, Any]:
    sessions = list_sessions(server, timeout=timeout)
    if session_id:
        for session in sessions:
            if session.get("id") == session_id:
                _validate_target_consistency(session, path=path, kernel_id=kernel_id)
                return session
        raise CommandError(f"No session matched id {session_id}.")
    if kernel_id:
        for session in sessions:
            if (session.get("kernel") or {}).get("id") == kernel_id:
                _validate_target_consistency(session, path=path, kernel_id=kernel_id)
                return session
        raise CommandError(f"No live session matched kernel id {kernel_id}.")
    if path:
        matches = [session for session in sessions if session.get("path") == path]
        if not matches:
            raise CommandError(f"No live session matched notebook path {path}.")
        if len(matches) > 1:
            ids = ", ".join(session["id"] for session in matches if session.get("id"))
            raise CommandError(
                f"Multiple live sessions matched notebook path {path}. Pass --session-id. Sessions: {ids}"
            )
        return matches[0]
    raise CommandError("Pass one of --path, --session-id, or --kernel-id.")


def _validate_target_consistency(
    session: dict[str, Any],
    *,
    path: str | None,
    kernel_id: str | None,
) -> None:
    session_path = session.get("path")
    session_kernel_id = (session.get("kernel") or {}).get("id")
    if path and session_path and session_path != path:
        raise CommandError(
            f"Conflicting live target selectors: session resolves to path {session_path!r}, not {path!r}."
        )
    if kernel_id and session_kernel_id and session_kernel_id != kernel_id:
        raise CommandError(
            f"Conflicting live target selectors: session resolves to kernel {session_kernel_id!r}, not {kernel_id!r}."
        )


def _resolve_kernel_target(
    server: ServerInfo,
    *,
    path: str | None,
    session_id: str | None,
    kernel_id: str | None,
    timeout: float,
) -> KernelTarget:
    session = _resolve_session(
        server,
        path=path,
        session_id=session_id,
        kernel_id=kernel_id,
        timeout=timeout,
    )
    resolved_kernel_id = kernel_id or (session.get("kernel") or {}).get("id")
    if not resolved_kernel_id:
        raise CommandError("Could not determine a kernel id for execution.")
    return KernelTarget(
        kernel_id=resolved_kernel_id,
        kernel_name=(session.get("kernel") or {}).get("name"),
        session_id=session.get("id"),
        path=session.get("path"),
    )


def _execute_request(
    server: ServerInfo,
    *,
    path: str | None,
    session_id: str | None,
    kernel_id: str | None,
    request: ExecuteRequest,
    transport: str,
    timeout: float,
) -> ExecutionResult:
    target = _resolve_kernel_target(
        server,
        path=path,
        session_id=session_id,
        kernel_id=kernel_id,
        timeout=timeout,
    )
    return _execute_request_with_target(
        server,
        target=target,
        request=request,
        transport=transport,
        timeout=timeout,
    )


def _ensure_kernel_idle(server: ServerInfo, kernel_id: str, timeout: float) -> None:
    """Wait for the kernel to be idle before attempting execution.

    Newly started or restarted kernels may not be ready for websocket
    connections even when the REST API reports idle.  A brief poll here
    prevents a class of flaky 'request_sent but recv failed' errors.
    """
    client = ServerClient(server, timeout=timeout)
    deadline = time.time() + min(timeout, 10.0)
    last_state: str | None = None
    while time.time() < deadline:
        try:
            model = _get_kernel_model(server, kernel_id, timeout=timeout, client=client)
        except HTTPCommandError:
            time.sleep(0.2)
            continue
        last_state = model.get("execution_state")
        if last_state in {"idle", None}:
            return
        time.sleep(0.2)
    if last_state == "starting":
        return
    raise CommandError(
        f"Timed out waiting for kernel {kernel_id} to become idle before execution. Last state: {last_state!r}."
    )


def _execute_request_with_target(
    server: ServerInfo,
    *,
    target: KernelTarget,
    request: ExecuteRequest,
    transport: str,
    timeout: float,
) -> ExecutionResult:
    attempts: list[str] = [transport]
    if transport == "auto":
        attempts = ["websocket", "zmq"]

    last_error: Exception | None = None
    for attempt in attempts:
        try:
            if attempt == "websocket":
                result = _execute_via_websocket(
                    server,
                    kernel_id=target.kernel_id,
                    session_id=target.session_id,
                    path=target.path,
                    request=request,
                    timeout=timeout,
                )
            elif attempt == "zmq":
                result = _execute_via_zmq(
                    kernel_id=target.kernel_id,
                    session_id=target.session_id,
                    path=target.path,
                    request=request,
                    timeout=timeout,
                )
            else:
                raise CommandError(f"Unknown transport {attempt!r}.")
            return result
        except TransportRetryUnsafeError as exc:
            if transport == "auto" and exc.request_sent:
                raise CommandError(
                    "Websocket execution may already have reached the kernel, so auto fallback was skipped "
                    "to avoid running the code twice."
                ) from exc
            last_error = exc
            continue
        except (
            CommandError,
            requests.RequestException,
            OSError,
            RuntimeError,
        ) as exc:  # RuntimeError: jupyter_client connection/timeout failures
            last_error = exc
            continue

    raise CommandError(f"Execution failed for all transports: {last_error}")


def execute_code(
    server: ServerInfo,
    *,
    path: str | None,
    session_id: str | None,
    kernel_id: str | None,
    code: str,
    transport: str,
    timeout: float,
    save_outputs: bool = False,
    cell_id: str | None = None,
) -> dict[str, Any]:
    result = _execute_request(
        server,
        path=path,
        session_id=session_id,
        kernel_id=kernel_id,
        request=ExecuteRequest(code=code),
        transport=transport,
        timeout=timeout,
    )
    result_dict = result.as_dict()

    outputs_saved = False
    if save_outputs and path and cell_id:
        model = _load_notebook_model(server, path, timeout=timeout)
        cells = model["content"].get("cells", [])
        matched = False
        for cell in cells:
            if cell.get("id") == cell_id and cell.get("cell_type") == "code":
                cell_outputs, exec_count = _events_to_notebook_outputs(result_dict.get("events") or [])
                cell["outputs"] = cell_outputs
                cell["execution_count"] = exec_count
                matched = True
                break
        if matched:
            _save_notebook_content(
                server,
                path,
                model["content"],
                timeout=timeout,
                expected_last_modified=model.get("last_modified"),
            )
            outputs_saved = True

    result_dict["outputs_saved"] = outputs_saved
    return result_dict


def _ws_url(server: ServerInfo, kernel_id: str, *, session_id: str | None = None) -> str:
    base = urljoin(server.ws_root_url, f"api/kernels/{kernel_id}/channels")
    params: dict[str, str] = {}
    if server.token:
        params["token"] = server.token
    if session_id:
        params["session_id"] = session_id
    if not params:
        return base
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}{urlencode(params)}"


def _message_type(msg: dict[str, Any]) -> str | None:
    return msg.get("msg_type") or (msg.get("header") or {}).get("msg_type")


def _message_parent_id(msg: dict[str, Any]) -> str | None:
    parent = msg.get("parent_header") or {}
    return parent.get("msg_id")


def _belongs_to_execution(msg: dict[str, Any], msg_id: str) -> bool:
    return _message_parent_id(msg) == msg_id


def _summarize_channel_message(msg: dict[str, Any]) -> dict[str, Any] | None:
    msg_type = _message_type(msg)
    content = msg.get("content") or {}
    if msg_type == "stream":
        return {"type": "stream", "name": content.get("name"), "text": content.get("text", "")}
    if msg_type == "execute_result":
        return {
            "type": "execute_result",
            "execution_count": content.get("execution_count"),
            "data": content.get("data", {}),
            "metadata": content.get("metadata", {}),
        }
    if msg_type == "display_data":
        return {"type": "display_data", "data": content.get("data", {}), "metadata": content.get("metadata", {})}
    if msg_type == "error":
        return {
            "type": "error",
            "ename": content.get("ename"),
            "evalue": content.get("evalue"),
            "traceback": content.get("traceback", []),
        }
    if msg_type == "execute_input":
        return {
            "type": "execute_input",
            "execution_count": content.get("execution_count"),
            "code": content.get("code", ""),
        }
    if msg_type == "status":
        return {"type": "status", "execution_state": content.get("execution_state")}
    return None


def _execute_via_websocket(
    server: ServerInfo,
    *,
    kernel_id: str,
    session_id: str | None,
    path: str | None,
    request: ExecuteRequest,
    timeout: float,
) -> ExecutionResult:
    # Kernel REST state can report ready before channels accept stable websocket traffic.
    # Keep this check bounded to avoid regressing steady-state execute throughput.
    _ensure_kernel_idle(server, kernel_id, min(timeout, 5.0))
    client = ServerClient(server, timeout=timeout)
    msg_id = uuid.uuid4().hex
    shell_session_id = uuid.uuid4().hex
    payload = {
        "header": {
            "msg_id": msg_id,
            "username": "agent",
            "session": shell_session_id,
            "msg_type": "execute_request",
            "version": "5.3",
        },
        "parent_header": {},
        "metadata": {},
        "content": {
            "code": request.code,
            "silent": request.silent,
            "store_history": request.store_history,
            "user_expressions": request.user_expressions,
            "allow_stdin": False,
            "stop_on_error": request.stop_on_error,
        },
        "channel": "shell",
        "buffers": [],
    }

    reply: dict[str, Any] | None = None
    events: list[dict[str, Any]] = []
    deadline = time.time() + timeout
    request_sent = False
    ws = None
    try:
        ws = websocket.create_connection(
            _ws_url(server, kernel_id, session_id=session_id),
            header=client.websocket_headers(),
            timeout=timeout,
        )
        ws.send(json.dumps(payload))
        request_sent = True

        while time.time() < deadline:
            raw = ws.recv()
            msg = json.loads(raw)
            if not _belongs_to_execution(msg, msg_id):
                continue
            summary = _summarize_channel_message(msg)
            if summary is not None:
                events.append(summary)
            msg_type = _message_type(msg)
            if msg_type == "execute_reply":
                reply = msg.get("content", {})
            if msg_type == "status" and (msg.get("content") or {}).get("execution_state") == "idle" and reply:
                break
        else:
            raise CommandError("Timed out waiting for kernel execution to finish over websocket.")
    except CommandError as exc:
        if request_sent:
            raise TransportRetryUnsafeError(
                _sanitize_error_text(str(exc), server_token=server.token),
                request_sent=True,
            ) from exc
        raise
    except (OSError, websocket.WebSocketException, json.JSONDecodeError) as exc:
        raise TransportRetryUnsafeError(
            _sanitize_error_text(str(exc), server_token=server.token),
            request_sent=request_sent,
        ) from exc
    finally:
        if ws is not None:
            ws.close()

    return ExecutionResult(
        transport="websocket",
        kernel_id=kernel_id,
        session_id=session_id,
        path=path,
        reply=reply or {},
        events=events,
    )


def _execute_via_zmq(
    *,
    kernel_id: str,
    session_id: str | None,
    path: str | None,
    request: ExecuteRequest,
    timeout: float,
) -> ExecutionResult:
    connection_file = find_connection_file(f"kernel-{kernel_id}.json")
    client = BlockingKernelClient(connection_file=connection_file)
    client.load_connection_file(connection_file)
    client.start_channels()
    events: list[dict[str, Any]] = []
    try:
        client.wait_for_ready(timeout=timeout)
        reply_msg = client.execute_interactive(
            request.code,
            silent=request.silent,
            store_history=request.store_history,
            user_expressions=request.user_expressions,
            allow_stdin=False,
            stop_on_error=request.stop_on_error,
            timeout=timeout,
            output_hook=lambda msg: _collect_output(events, msg),
        )
    finally:
        client.stop_channels()

    return ExecutionResult(
        transport="zmq",
        kernel_id=kernel_id,
        session_id=session_id,
        path=path,
        reply=(reply_msg.get("content") or {}),
        events=events,
    )


def _collect_output(events: list[dict[str, Any]], msg: dict[str, Any]) -> None:
    summary = _summarize_channel_message(msg)
    if summary is not None:
        events.append(summary)


def _get_kernel_model(
    server: ServerInfo,
    kernel_id: str,
    timeout: float = DEFAULT_TIMEOUT,
    *,
    client: ServerClient | None = None,
) -> dict[str, Any]:
    client = client or ServerClient(server, timeout=timeout)
    return client.request("GET", f"api/kernels/{quote(kernel_id, safe='')}", timeout=timeout)


def _wait_for_kernel_idle(server: ServerInfo, kernel_id: str, timeout: float) -> dict[str, Any]:
    client = ServerClient(server, timeout=timeout)
    deadline = time.time() + timeout
    last_state: str | None = None
    while time.time() < deadline:
        try:
            model = _get_kernel_model(server, kernel_id, timeout=timeout, client=client)
        except HTTPCommandError as exc:
            if exc.status_code == 404:
                time.sleep(0.2)
                continue
            raise
        last_state = model.get("execution_state")
        if last_state == "idle":
            return model
        time.sleep(0.2)
    raise CommandError(
        f"Timed out waiting for kernel {kernel_id} to become idle after restart. Last state: {last_state!r}."
    )


def restart_kernel(
    server: ServerInfo,
    *,
    path: str | None,
    session_id: str | None,
    kernel_id: str | None,
    timeout: float,
) -> dict[str, Any]:
    target = _resolve_kernel_target(
        server,
        path=path,
        session_id=session_id,
        kernel_id=kernel_id,
        timeout=timeout,
    )
    client = ServerClient(server, timeout=timeout)
    client.request("POST", f"api/kernels/{quote(target.kernel_id, safe='')}/restart", timeout=timeout)
    model = _wait_for_kernel_idle(server, target.kernel_id, timeout=timeout)
    return {
        "operation": "restart-kernel",
        "kernel_id": target.kernel_id,
        "kernel_name": target.kernel_name,
        "session_id": target.session_id,
        "path": target.path,
        "kernel": {
            "id": model.get("id"),
            "name": model.get("name"),
            "execution_state": model.get("execution_state"),
            "last_activity": model.get("last_activity"),
            "connections": model.get("connections"),
        },
    }


def _require_notebook_session(target: KernelTarget, feature: str) -> None:
    if not target.path:
        raise CommandError(f"{feature} requires a notebook path.")
    if not target.session_id:
        raise CommandError(f"{feature} requires a live notebook session, not just a bare kernel id.")


def _bounded_positive_int(value: int, *, name: str, maximum: int) -> int:
    if value < 1:
        raise CommandError(f"{name} must be at least 1.")
    if value > maximum:
        raise CommandError(f"{name} must be at most {maximum}.")
    return value


def _source_preview(source: str, limit: int = 120) -> str:
    single_line = " ".join(source.split())
    if len(single_line) <= limit:
        return single_line
    return f"{single_line[: limit - 3]}..."


def run_all_cells(
    server: ServerInfo,
    *,
    path: str | None,
    session_id: str | None,
    kernel_id: str | None,
    transport: str,
    timeout: float,
    save_outputs: bool = False,
) -> dict[str, Any]:
    target = _resolve_kernel_target(
        server,
        path=path,
        session_id=session_id,
        kernel_id=kernel_id,
        timeout=timeout,
    )
    _require_notebook_session(target, "Run-all")
    notebook_path = path or target.path

    model = _load_notebook_model(server, notebook_path, timeout=timeout)
    snapshot_sha256 = hashlib.sha256(json.dumps(model["content"], sort_keys=True).encode("utf-8")).hexdigest()
    results: list[dict[str, Any]] = []
    executed_cell_count = 0
    skipped_cell_count = 0
    overall_status = "ok"
    failed_cell: dict[str, Any] | None = None

    for cell_index, cell in enumerate(model["content"]["cells"]):
        if cell.get("cell_type") != "code":
            continue
        source = cell.get("source", "")
        if not source.strip():
            skipped_cell_count += 1
            results.append(
                {
                    "index": cell_index,
                    "cell_id": cell.get("id"),
                    "status": "skipped",
                    "reason": "empty-source",
                    "source_preview": _source_preview(source),
                }
            )
            continue

        executed_cell_count += 1
        result = _execute_request_with_target(
            server,
            target=target,
            request=ExecuteRequest(code=source),
            transport=transport,
            timeout=timeout,
        ).as_dict()
        cell_result = {
            "index": cell_index,
            "cell_id": cell.get("id"),
            "source_preview": _source_preview(source),
            "status": result.get("status"),
            "transport": result.get("transport"),
            "reply": result.get("reply"),
            "events": result.get("events"),
        }
        results.append(cell_result)

        if save_outputs:
            cell_outputs, exec_count = _events_to_notebook_outputs(result.get("events") or [])
            cell["outputs"] = cell_outputs
            cell["execution_count"] = exec_count

        if result.get("status") != "ok":
            overall_status = "error"
            failed_cell = cell_result
            break

    outputs_saved = False
    if save_outputs:
        _save_run_all_outputs(
            server,
            notebook_path,
            executed_model=model["content"],
            timeout=timeout,
        )
        outputs_saved = True

    note = (
        "Run-all executed and saved outputs back to the notebook file."
        if outputs_saved
        else "Run-all executes against the live kernel for verification and does not persist notebook outputs."
    )

    return {
        "operation": "run-all",
        "path": notebook_path,
        "kernel_id": target.kernel_id,
        "kernel_name": target.kernel_name,
        "session_id": target.session_id,
        "snapshot_last_modified": model.get("last_modified"),
        "snapshot_sha256": snapshot_sha256,
        "transport_requested": transport,
        "timeout_per_cell_seconds": timeout,
        "status": overall_status,
        "executed_cell_count": executed_cell_count,
        "skipped_cell_count": skipped_cell_count,
        "failed_cell": failed_cell,
        "cells": results,
        "outputs_saved": outputs_saved,
        "note": note,
    }


def restart_and_run_all(
    server: ServerInfo,
    *,
    path: str | None,
    session_id: str | None,
    kernel_id: str | None,
    transport: str,
    timeout: float,
    save_outputs: bool = False,
) -> dict[str, Any]:
    target = _resolve_kernel_target(
        server,
        path=path,
        session_id=session_id,
        kernel_id=kernel_id,
        timeout=timeout,
    )
    _require_notebook_session(target, "Restart-run-all")
    restart = restart_kernel(
        server,
        path=target.path,
        session_id=target.session_id,
        kernel_id=target.kernel_id,
        timeout=timeout,
    )
    run_all = run_all_cells(
        server,
        path=target.path,
        session_id=target.session_id,
        kernel_id=target.kernel_id,
        transport=transport,
        timeout=timeout,
        save_outputs=save_outputs,
    )
    return {
        "operation": "restart-run-all",
        "restart": restart,
        "run_all": run_all,
        "note": (
            "Restart-run-all is explicit verification mode; "
            "prefer incremental execute/edit unless the user asked for a fresh run."
        ),
    }


def _parse_text_plain_literal(value: str) -> Any:
    try:
        return ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return value


def _user_expression_value(reply: dict[str, Any], name: str) -> Any:
    user_expressions = reply.get("user_expressions") or {}
    expression_result = user_expressions.get(name)
    if not expression_result:
        raise CommandError(f"Kernel did not return a value for user expression {name!r}.")
    if expression_result.get("status") != "ok":
        raise CommandError(f"User expression {name!r} failed: {expression_result}")
    data = expression_result.get("data") or {}
    if "application/json" in data:
        return data["application/json"]
    if "text/plain" in data:
        return _parse_text_plain_literal(data["text/plain"])
    return expression_result


def _sanitize_error_text(text: str, *, server_token: str | None = None) -> str:
    redacted = re.sub(r"([?&]token=)([^&\s]+)", r"\1[REDACTED]", text)
    if server_token:
        redacted = redacted.replace(server_token, "[REDACTED]")
    return redacted


def _python_variable_list_expression(*, limit: int, include_private: bool, include_callables: bool) -> str:
    private_filter = "True" if include_private else "not name.startswith('_')"
    callable_filter = "True" if include_callables else "not callable(value)"
    excluded = ("In", "Out", "exit", "quit", "get_ipython")
    return (
        "[{'name': name, "
        "'type': type(value).__name__, "
        "'module': type(value).__module__} "
        "for name, value in sorted(globals().items()) "
        f"if name not in {excluded!r} "
        f"and ({private_filter}) "
        f"and ({callable_filter}) "
        "and type(value).__name__ != 'module']"
        f"[:{limit}]"
    )


def _python_variable_preview_expression(name: str, *, max_chars: int) -> str:
    template = """
(
lambda _name, _limit:
    None if _name not in globals() else
    (lambda _value, _simple: {
        'name': _name,
        'type': type(_value).__name__,
        'module': type(_value).__module__,
        'preview': (
            _value[:_limit] if isinstance(_value, str) else
            _value.decode('utf-8', 'replace')[:_limit] if isinstance(_value, bytes) else
            _value if isinstance(_value, (type(None), bool, int, float)) else
            repr(_value)[:_limit] if isinstance(_value, complex) else
            {
                'kind': type(_value).__name__,
                'length': len(_value),
                'items': [_simple(item) for item in list(_value)[:5]],
            } if isinstance(_value, (list, tuple, set)) else
            {
                'kind': 'dict',
                'length': len(_value),
                'items': [
                    {'key': _simple(key), 'value': _simple(value)}
                    for key, value in list(_value.items())[:5]
                ],
            } if isinstance(_value, dict) else
            f'<{type(_value).__module__}.{type(_value).__name__}>'
        )
    })(
        globals()[_name],
        lambda _item: (
            _item[:_limit] if isinstance(_item, str) else
            _item.decode('utf-8', 'replace')[:_limit] if isinstance(_item, bytes) else
            _item if isinstance(_item, (type(None), bool, int, float)) else
            repr(_item)[:_limit] if isinstance(_item, complex) else
            f'<{type(_item).__module__}.{type(_item).__name__}>'
        )
    )
)({name!r}, {max_chars})
"""
    return template.format(name=name, max_chars=max_chars).strip()


def _ensure_python_kernel(target: KernelTarget, feature: str) -> None:
    if target.kernel_name and "python" in target.kernel_name.lower():
        return
    raise CommandError(f"{feature} currently supports Python kernels only. Resolved kernel: {target.kernel_name!r}.")


def list_variables(
    server: ServerInfo,
    *,
    path: str | None,
    session_id: str | None,
    kernel_id: str | None,
    transport: str,
    timeout: float,
    limit: int,
    include_private: bool,
    include_callables: bool,
) -> dict[str, Any]:
    limit = _bounded_positive_int(limit, name="limit", maximum=100)
    target = _resolve_kernel_target(
        server,
        path=path,
        session_id=session_id,
        kernel_id=kernel_id,
        timeout=timeout,
    )
    _ensure_python_kernel(target, "Variable listing")
    result = _execute_request(
        server,
        path=target.path,
        session_id=target.session_id,
        kernel_id=target.kernel_id,
        request=ExecuteRequest(
            code="",
            silent=True,
            store_history=False,
            user_expressions={
                "codex_variables": _python_variable_list_expression(
                    limit=limit,
                    include_private=include_private,
                    include_callables=include_callables,
                )
            },
        ),
        transport=transport,
        timeout=timeout,
    ).as_dict()
    variables = _user_expression_value(result.get("reply") or {}, "codex_variables")
    return {
        "operation": "variables-list",
        "kernel_id": target.kernel_id,
        "kernel_name": target.kernel_name,
        "session_id": target.session_id,
        "path": target.path,
        "transport": result.get("transport"),
        "limit": limit,
        "variables": variables,
        "note": "Variable listing uses bounded Python-kernel introspection and does not persist notebook state.",
    }


def preview_variable(
    server: ServerInfo,
    *,
    path: str | None,
    session_id: str | None,
    kernel_id: str | None,
    transport: str,
    timeout: float,
    name: str,
    max_chars: int,
) -> dict[str, Any]:
    if not name.isidentifier():
        raise CommandError(f"Variable name {name!r} is not a valid Python identifier.")
    max_chars = _bounded_positive_int(max_chars, name="max-chars", maximum=2000)
    target = _resolve_kernel_target(
        server,
        path=path,
        session_id=session_id,
        kernel_id=kernel_id,
        timeout=timeout,
    )
    _ensure_python_kernel(target, "Variable preview")
    result = _execute_request(
        server,
        path=target.path,
        session_id=target.session_id,
        kernel_id=target.kernel_id,
        request=ExecuteRequest(
            code="",
            silent=True,
            store_history=False,
            user_expressions={"codex_variable": _python_variable_preview_expression(name, max_chars=max_chars)},
        ),
        transport=transport,
        timeout=timeout,
    ).as_dict()
    payload = _user_expression_value(result.get("reply") or {}, "codex_variable")
    if payload is None:
        raise CommandError(f"No live variable matched name {name!r}.")
    return {
        "operation": "variable-preview",
        "kernel_id": target.kernel_id,
        "kernel_name": target.kernel_name,
        "session_id": target.session_id,
        "path": target.path,
        "transport": result.get("transport"),
        "variable": payload,
        "note": "Variable preview is bounded and avoids arbitrary repr calls for non-scalar objects.",
    }


def _read_text_argument(value: str | None, file_path: str | None, purpose: str) -> str:
    if value is not None:
        return value
    if file_path:
        return Path(file_path).read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise CommandError(f"Provide {purpose} with --{purpose}, --{purpose}-file, or stdin.")


def _read_code_argument(code: str | None, code_file: str | None) -> str:
    return _read_text_argument(code, code_file, "code")


def _read_source_argument(source: str | None, source_file: str | None) -> str:
    return _read_text_argument(source, source_file, "source")


def _print(data: Any, compact: bool) -> None:
    if compact:
        print(json.dumps(data, separators=(",", ":"), sort_keys=True))
        return
    print(json.dumps(data, indent=2, sort_keys=True))


def _add_server_selection(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--server-url")
    parser.add_argument("--port", type=int)


def _add_live_target_selection(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--path")
    parser.add_argument("--session-id")
    parser.add_argument("--kernel-id")


def _add_cell_selector(parser: argparse.ArgumentParser, *, required: bool = True) -> None:
    group = parser.add_mutually_exclusive_group(required=required)
    group.add_argument("--index", type=int)
    group.add_argument("--cell-id")


def _resolve_insert_index(args: argparse.Namespace) -> int:
    if args.at_index is not None:
        return args.at_index
    if args.before is not None:
        return args.before
    if args.after is not None:
        return args.after + 1
    raise CommandError("Pass one of --at-index, --before, or --after.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect live Jupyter servers and execute code in running kernels.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    servers_parser = subparsers.add_parser("servers", help="List discovered running Jupyter servers.")
    servers_parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    servers_parser.add_argument("--compact", action="store_true")

    notebooks_parser = subparsers.add_parser(
        "notebooks", help="List live notebook sessions plus notebook tabs discovered from JupyterLab workspaces."
    )
    _add_server_selection(notebooks_parser)
    notebooks_parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    notebooks_parser.add_argument("--compact", action="store_true")

    contents_parser = subparsers.add_parser("contents", help="Fetch saved notebook contents through the Contents API.")
    _add_server_selection(contents_parser)
    contents_parser.add_argument("--path", required=True)
    contents_parser.add_argument("--include-outputs", action="store_true")
    contents_parser.add_argument("--raw", action="store_true")
    contents_parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    contents_parser.add_argument("--compact", action="store_true")

    execute_parser = subparsers.add_parser("execute", help="Execute code incrementally in a live notebook kernel.")
    _add_server_selection(execute_parser)
    _add_live_target_selection(execute_parser)
    execute_parser.add_argument("--code")
    execute_parser.add_argument("--code-file")
    execute_parser.add_argument("--transport", choices=["auto", "websocket", "zmq"], default="auto")
    execute_parser.add_argument("--timeout", type=float, default=DEFAULT_EXEC_TIMEOUT)
    execute_parser.add_argument(
        "--save-outputs",
        action="store_true",
        help=(
            "Save cell outputs back to the notebook file. Requires --path and --cell-id. "
            "Automatically enabled when --cell-id is provided."
        ),
    )
    execute_parser.add_argument(
        "--no-save-outputs",
        action="store_true",
        help=("Disable automatic output saving even when --cell-id is provided. Useful for pure REPL usage."),
    )
    execute_parser.add_argument(
        "--cell-id",
        help=(
            "Target cell ID. When provided, outputs are automatically saved back to the "
            "notebook file unless --no-save-outputs is set."
        ),
    )
    execute_parser.add_argument("--compact", action="store_true")

    restart_parser = subparsers.add_parser("restart", help="Restart a live notebook kernel.")
    _add_server_selection(restart_parser)
    _add_live_target_selection(restart_parser)
    restart_parser.add_argument("--timeout", type=float, default=DEFAULT_EXEC_TIMEOUT)
    restart_parser.add_argument("--compact", action="store_true")

    run_all_parser = subparsers.add_parser(
        "run-all",
        help="Execute all notebook code cells against the live kernel.",
    )
    _add_server_selection(run_all_parser)
    _add_live_target_selection(run_all_parser)
    run_all_parser.add_argument("--transport", choices=["auto", "websocket", "zmq"], default="auto")
    run_all_parser.add_argument("--timeout", type=float, default=DEFAULT_EXEC_TIMEOUT)
    run_all_parser.add_argument(
        "--save-outputs",
        action="store_true",
        help="Save cell outputs back to the notebook file.",
    )
    run_all_parser.add_argument("--compact", action="store_true")

    restart_run_all_parser = subparsers.add_parser(
        "restart-run-all",
        help="Restart the live kernel and then run all notebook code cells.",
    )
    _add_server_selection(restart_run_all_parser)
    _add_live_target_selection(restart_run_all_parser)
    restart_run_all_parser.add_argument("--transport", choices=["auto", "websocket", "zmq"], default="auto")
    restart_run_all_parser.add_argument("--timeout", type=float, default=DEFAULT_EXEC_TIMEOUT)
    restart_run_all_parser.add_argument(
        "--save-outputs",
        action="store_true",
        help="Save cell outputs back to the notebook file.",
    )
    restart_run_all_parser.add_argument("--compact", action="store_true")

    edit_parser = subparsers.add_parser("edit", help="Edit saved notebook cells through the Contents API.")
    _add_server_selection(edit_parser)
    edit_parser.add_argument("--path", required=True)
    edit_parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    edit_subparsers = edit_parser.add_subparsers(dest="edit_command", required=True)

    replace_parser = edit_subparsers.add_parser("replace-source", help="Replace the source of an existing cell.")
    _add_cell_selector(replace_parser)
    replace_parser.add_argument("--source")
    replace_parser.add_argument("--source-file")
    replace_parser.add_argument("--compact", action="store_true")

    insert_parser = edit_subparsers.add_parser("insert", help="Insert a new cell into the notebook.")
    location_group = insert_parser.add_mutually_exclusive_group(required=True)
    location_group.add_argument("--at-index", type=int)
    location_group.add_argument("--before", type=int)
    location_group.add_argument("--after", type=int)
    insert_parser.add_argument("--cell-type", choices=["code", "markdown", "raw"], required=True)
    insert_parser.add_argument("--source")
    insert_parser.add_argument("--source-file")
    insert_parser.add_argument("--compact", action="store_true")

    delete_parser = edit_subparsers.add_parser("delete", help="Delete a cell from the notebook.")
    _add_cell_selector(delete_parser)
    delete_parser.add_argument("--compact", action="store_true")

    move_parser = edit_subparsers.add_parser("move", help="Move a cell to a different index.")
    _add_cell_selector(move_parser)
    move_parser.add_argument("--to-index", type=int, required=True)
    move_parser.add_argument("--compact", action="store_true")

    clear_outputs_parser = edit_subparsers.add_parser(
        "clear-outputs",
        help="Clear saved outputs and execution counts for code cells.",
    )
    clear_outputs_group = clear_outputs_parser.add_mutually_exclusive_group(required=False)
    clear_outputs_group.add_argument("--all", action="store_true")
    clear_outputs_group.add_argument("--index", type=int)
    clear_outputs_group.add_argument("--cell-id")
    clear_outputs_parser.add_argument("--compact", action="store_true")

    variables_parser = subparsers.add_parser(
        "variables",
        help="Inspect live Python-kernel variables with bounded previews.",
    )
    _add_server_selection(variables_parser)
    _add_live_target_selection(variables_parser)
    variables_parser.add_argument("--transport", choices=["auto", "websocket", "zmq"], default="auto")
    variables_parser.add_argument("--timeout", type=float, default=DEFAULT_EXEC_TIMEOUT)
    variables_subparsers = variables_parser.add_subparsers(dest="variables_command", required=True)

    variables_list_parser = variables_subparsers.add_parser("list", help="List live variables in the kernel.")
    variables_list_parser.add_argument("--limit", type=int, default=25)
    variables_list_parser.add_argument("--include-private", action="store_true")
    variables_list_parser.add_argument("--include-callables", action="store_true")
    variables_list_parser.add_argument("--compact", action="store_true")

    variables_preview_parser = variables_subparsers.add_parser(
        "preview",
        help="Show a bounded preview of a live variable in the kernel.",
    )
    variables_preview_parser.add_argument("--name", required=True)
    variables_preview_parser.add_argument("--max-chars", type=int, default=400)
    variables_preview_parser.add_argument("--compact", action="store_true")

    return parser


def _resolve_execute_code(server: Any, args: argparse.Namespace) -> str:
    if args.code is None and args.code_file is None and args.cell_id and args.path:
        model = _load_notebook_model(server, args.path)
        for cell in model["content"].get("cells", []):
            if cell.get("id") == args.cell_id:
                return str(cell.get("source", ""))
        raise CommandError(f"Cell id {args.cell_id!r} not found in {args.path!r}")
    return _read_code_argument(args.code, args.code_file)


def _run_execute(server: Any, args: argparse.Namespace) -> None:
    _print(
        execute_code(
            server,
            path=args.path,
            session_id=args.session_id,
            kernel_id=args.kernel_id,
            code=_resolve_execute_code(server, args),
            transport=args.transport,
            timeout=args.timeout,
            save_outputs=(args.save_outputs or bool(args.cell_id)) and not args.no_save_outputs,
            cell_id=args.cell_id,
        ),
        args.compact,
    )


def _run_edit(server: Any, args: argparse.Namespace) -> dict[str, Any]:
    if args.edit_command == "replace-source":
        return edit_cell_source(
            server,
            path=args.path,
            index=args.index,
            cell_id=args.cell_id,
            source=_read_source_argument(args.source, args.source_file),
            timeout=args.timeout,
        )
    if args.edit_command == "insert":
        return insert_cell(
            server,
            path=args.path,
            cell_type=args.cell_type,
            source=_read_source_argument(args.source, args.source_file),
            at_index=_resolve_insert_index(args),
            timeout=args.timeout,
        )
    if args.edit_command == "delete":
        return delete_cell(
            server,
            path=args.path,
            index=args.index,
            cell_id=args.cell_id,
            timeout=args.timeout,
        )
    if args.edit_command == "move":
        return move_cell(
            server,
            path=args.path,
            index=args.index,
            cell_id=args.cell_id,
            to_index=args.to_index,
            timeout=args.timeout,
        )
    if args.edit_command == "clear-outputs":
        return clear_cell_outputs(
            server,
            path=args.path,
            index=args.index,
            cell_id=args.cell_id,
            all_cells=args.all,
            timeout=args.timeout,
        )
    raise CommandError(f"Unknown edit command {args.edit_command!r}.")


def _run_variables(server: Any, args: argparse.Namespace) -> dict[str, Any]:
    if args.variables_command == "list":
        return list_variables(
            server,
            path=args.path,
            session_id=args.session_id,
            kernel_id=args.kernel_id,
            transport=args.transport,
            timeout=args.timeout,
            limit=args.limit,
            include_private=args.include_private,
            include_callables=args.include_callables,
        )
    if args.variables_command == "preview":
        return preview_variable(
            server,
            path=args.path,
            session_id=args.session_id,
            kernel_id=args.kernel_id,
            transport=args.transport,
            timeout=args.timeout,
            name=args.name,
            max_chars=args.max_chars,
        )
    raise CommandError(f"Unknown variables command {args.variables_command!r}.")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    server_token: str | None = None
    try:
        if args.command == "servers":
            _print({"servers": discover_servers(timeout=args.timeout)}, args.compact)
            return 0

        server = _select_server(server_url=args.server_url, port=args.port, timeout=args.timeout)
        server_token = server.token

        if args.command == "notebooks":
            _print(combined_open_notebooks(server, timeout=args.timeout), args.compact)
            return 0

        if args.command == "contents":
            _print(
                get_contents(
                    server,
                    args.path,
                    include_outputs=args.include_outputs,
                    raw=args.raw,
                    timeout=args.timeout,
                ),
                args.compact,
            )
            return 0

        if args.command == "execute":
            _run_execute(server, args)
            return 0

        if args.command == "restart":
            _print(
                restart_kernel(
                    server,
                    path=args.path,
                    session_id=args.session_id,
                    kernel_id=args.kernel_id,
                    timeout=args.timeout,
                ),
                args.compact,
            )
            return 0

        if args.command == "run-all":
            result = run_all_cells(
                server,
                path=args.path,
                session_id=args.session_id,
                kernel_id=args.kernel_id,
                transport=args.transport,
                timeout=args.timeout,
                save_outputs=args.save_outputs,
            )
            _print(result, args.compact)
            return 0 if result.get("status") == "ok" else 1

        if args.command == "restart-run-all":
            result = restart_and_run_all(
                server,
                path=args.path,
                session_id=args.session_id,
                kernel_id=args.kernel_id,
                transport=args.transport,
                timeout=args.timeout,
                save_outputs=args.save_outputs,
            )
            _print(result, args.compact)
            return 0 if (result.get("run_all") or {}).get("status") == "ok" else 1

        if args.command == "edit":
            _print(_run_edit(server, args), args.compact)
            return 0

        if args.command == "variables":
            _print(_run_variables(server, args), args.compact)
            return 0
    except CommandError as exc:
        token = server_token
        print(json.dumps({"error": _sanitize_error_text(str(exc), server_token=token)}, indent=2), file=sys.stderr)
        return 1
    except (
        DEFENSIVE_OP_ERRORS,
        requests.RequestException,
        websocket.WebSocketException,
    ) as exc:  # pragma: no cover - defensive CLI surface
        token = server_token
        message = _sanitize_error_text(f"Unexpected error: {exc}", server_token=token)
        print(json.dumps({"error": message}, indent=2), file=sys.stderr)
        return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
