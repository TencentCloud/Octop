"""JSON-RPC handlers for the Octop Memory bridge adapter."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from octop_memory.adapters.bridge import PROTOCOL_VERSION
from octop_memory.application import dashboard_data
from octop_memory.application.config import MemoryRuntimeConfig
from octop_memory.application.host_files import HostFilesIndex
from octop_memory.application.path_projection import PathError
from octop_memory.application.runtime import (
    MemoryRuntime,
    _HostFileUnavailableError,
    _NotFoundError,
)
from octop_memory.ports.llm import LLMClient
from octop_memory.storage.driver_errors import REPORTABLE_ERRORS

if TYPE_CHECKING:
    from octop_memory.core import Memory

logger = logging.getLogger(__name__)

# JSON-RPC error codes. Protocol errors use the reserved JSON-RPC range;
# application errors live in -32000..-32099.
ERR_PARSE = -32700
ERR_INVALID_REQUEST = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL = -32603
ERR_PATH_NOT_FOUND = -32010
ERR_PATH_INVALID = -32011
ERR_HOST_FILE_UNAVAILABLE = -32012


class Bridge:
    """JSON-RPC adapter over :class:`octop_memory.application.runtime.MemoryRuntime`."""

    def __init__(
        self,
        memory: Memory,
        *,
        host_files: HostFilesIndex | None = None,
        config: MemoryRuntimeConfig | dict[str, Any] | None = None,
        llm: LLMClient | None = None,
    ) -> None:
        self._memory = memory
        self._runtime = MemoryRuntime(memory, host_files=host_files, config=config, llm=llm)
        self._dispatch: dict[str, Any] = {
            "handshake": self._handshake,
            "stats": self._runtime.stats,
            "reindex": self._runtime.reindex,
            "memory_search": self._runtime.memory_search,
            "memory_get": self._runtime.memory_get,
            "capture": self._runtime.capture,
            "extract": self._runtime.extract,
            "promote": self._runtime.promote,
            "reconcile_manual_documents": self._runtime.reconcile_manual_documents,
            "manual_document_review_status": self._runtime.manual_document_review_status,
        }
        self._dispatch.update(dashboard_data.build_dispatch(memory))

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a single JSON-RPC request to a response dict."""
        rpc_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}

        if not isinstance(method, str):
            return _error(rpc_id, ERR_INVALID_REQUEST, "request missing 'method' string")
        if not isinstance(params, dict):
            return _error(rpc_id, ERR_INVALID_PARAMS, "'params' must be an object")

        handler = self._dispatch.get(method)
        if handler is None:
            return _error(rpc_id, ERR_METHOD_NOT_FOUND, f"unknown method {method!r}")

        try:
            result = handler(params)
        except _NotFoundError as exc:
            return _error(rpc_id, ERR_PATH_NOT_FOUND, str(exc))
        except dashboard_data._NotFoundError as exc:
            return _error(rpc_id, ERR_PATH_NOT_FOUND, str(exc))
        except _HostFileUnavailableError as exc:
            return _error(rpc_id, ERR_HOST_FILE_UNAVAILABLE, str(exc))
        except PathError as exc:
            return _error(rpc_id, ERR_PATH_INVALID, str(exc))
        except ValueError as exc:
            return _error(rpc_id, ERR_INVALID_PARAMS, str(exc))
        except REPORTABLE_ERRORS as exc:
            logger.exception("bridge handler %s failed", method)
            return _error(rpc_id, ERR_INTERNAL, f"{type(exc).__name__}: {exc}")

        return {"jsonrpc": "2.0", "id": rpc_id, "result": result}

    def _handshake(self, params: dict[str, Any]) -> dict[str, Any]:
        client_version = params.get("client_version")
        return {
            "protocol_version": PROTOCOL_VERSION,
            "client_version": client_version,
            "server": "octop-memory.bridge",
            "namespace": self._memory.namespace,
        }


def _error(rpc_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "error": {"code": code, "message": message},
    }


__all__ = [
    "ERR_HOST_FILE_UNAVAILABLE",
    "ERR_INTERNAL",
    "ERR_INVALID_PARAMS",
    "ERR_INVALID_REQUEST",
    "ERR_METHOD_NOT_FOUND",
    "ERR_PARSE",
    "ERR_PATH_INVALID",
    "ERR_PATH_NOT_FOUND",
    "Bridge",
    "_error",
]
