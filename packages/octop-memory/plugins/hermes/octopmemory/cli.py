"""Optional Hermes CLI hooks for the OctopMemory provider.

Hermes exposes these commands only when ``memory.provider`` is set to
``octopmemory``. Commands are intentionally small diagnostics around the
same ``memory_search`` / ``memory_get`` contract exposed to the model.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:  # pragma: no cover - present inside Hermes
    from hermes_constants import get_hermes_home as _get_hermes_home
except ImportError:  # pragma: no cover - local tests run outside Hermes
    _get_hermes_home = None


def _octopmemory_command(args) -> None:  # pragma: no cover - exercised in Hermes
    sub = getattr(args, "octopmemory_command", None)
    if sub == "status":
        provider = _new_provider(args)
        try:
            print(f"OctopMemory provider: {provider.name}")
            print(f"Available: {provider.is_available()}")
            print("Tools: memory_search, memory_get")
        finally:
            provider.shutdown()
    elif sub == "search":
        provider = _new_provider(args)
        try:
            result = json.loads(
                provider.handle_tool_call(
                    "memory_search",
                    {
                        "query": str(getattr(args, "query", "")),
                        "maxResults": _positive_int(getattr(args, "max", None), 5),
                        "corpus": getattr(args, "corpus", "all") or "all",
                    },
                )
            )
            hits = result.get("hits", [])
            if not hits:
                print("No matches.")
                return
            for hit in hits:
                path = hit.get("path", "")
                layer = hit.get("layer", "")
                snippet = str(hit.get("snippet", "")).replace("\n", " ")
                print(f"{path} [{layer}] {snippet}")
        finally:
            provider.shutdown()
    elif sub == "show":
        provider = _new_provider(args)
        try:
            params: dict[str, Any] = {"path": str(getattr(args, "path", "")), "corpus": getattr(args, "corpus", "all")}
            from_line = _positive_int(getattr(args, "from_line", None), 0)
            lines = _positive_int(getattr(args, "lines", None), 0)
            if from_line > 0:
                params["from"] = from_line
            if lines > 0:
                params["lines"] = lines
            result = json.loads(provider.handle_tool_call("memory_get", params))
            if "code" in result and "message" in result:
                print(f"Error: {result['message']}")
                return
            print(f"# {result.get('path', params['path'])}")
            excerpt = result.get("excerpt", "")
            if excerpt:
                print(excerpt)
        finally:
            provider.shutdown()
    else:
        print("Usage: hermes octopmemory <status|search|show>")


def register_cli(subparser) -> None:  # pragma: no cover - exercised in Hermes
    subparser.add_argument("--hermes-home", help="Hermes home directory; defaults to active Hermes profile home")
    subs = subparser.add_subparsers(dest="octopmemory_command")
    subs.add_parser("status", help="Show OctopMemory provider status")

    search = subs.add_parser("search", help="Search OctopMemory via memory_search")
    search.add_argument("query", help="Search query")
    search.add_argument("-n", "--max", default=5, help="Maximum number of hits")
    search.add_argument("--corpus", default="all", choices=["all", "memory", "sessions", "wiki"])

    show = subs.add_parser("show", help="Read one OctopMemory path via memory_get")
    show.add_argument("path", help="Path returned by memory_search")
    show.add_argument("--from", dest="from_line", default=None, help="1-based start line")
    show.add_argument("--lines", default=None, help="Number of lines to return")
    show.add_argument("--corpus", default="all", choices=["all", "memory", "wiki"])

    subparser.set_defaults(func=_octopmemory_command)


def _new_provider(args):
    cls = _load_provider_class()
    provider = cls()
    provider.initialize("octopmemory-cli", hermes_home=str(_resolve_hermes_home(args)), platform="cli")
    return provider


def _resolve_hermes_home(args) -> Path:
    explicit = getattr(args, "hermes_home", None)
    if explicit:
        return Path(str(explicit)).expanduser().resolve()
    if _get_hermes_home is not None:
        try:
            return Path(_get_hermes_home()).expanduser().resolve()
        except (OSError, RuntimeError, ValueError, TypeError):
            logger.warning("hermes home lookup failed; using HERMES_HOME", exc_info=True)
    return Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser().resolve()


def _load_provider_class():
    init_path = Path(__file__).with_name("__init__.py")
    spec = importlib.util.spec_from_file_location("_octopmemory_provider_for_cli", init_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load OctopMemory provider from {init_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.OctopMemoryProvider


def _positive_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback
