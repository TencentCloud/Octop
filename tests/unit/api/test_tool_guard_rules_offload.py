"""Reading the guard rules must not run on the event loop."""

from __future__ import annotations

import asyncio
import threading

from octop.api.routers import security as security_router


class _Store:
    def __init__(self):
        self.threads: list[int] = []

    def list_catalog(self):
        self.threads.append(threading.get_ident())
        return [{"id": "r1"}]

    def read_text(self) -> str:
        self.threads.append(threading.get_ident())
        return "rules: []\n"

    def display_path(self) -> str:
        return "~/.octop/security/tool_guard/rules.yaml"


class _Server:
    def __init__(self, store):
        self.app_runtime = type(
            "R", (), {"agent_registry": type("G", (), {"tool_guard_rules": store})()}
        )()


def test_both_rule_handlers_offload_the_store_reads():
    """Source-level: both handlers must go through asyncio.to_thread."""
    import inspect

    source = inspect.getsource(security_router)

    assert "asyncio.to_thread(store.list_catalog)" in source
    assert "asyncio.to_thread(store.read_text)" in source


def test_raw_rules_read_off_the_event_loop():
    store = _Store()
    seen: dict[str, int] = {}

    async def _go():
        seen["loop"] = threading.get_ident()
        return await security_router.get_tool_guard_rules_raw(_=None, server=_Server(store))

    response = asyncio.run(_go())

    assert response.content == "rules: []\n"
    assert store.threads and seen["loop"] not in store.threads
