"""Async callers must get the adapted methods, not the raw legacy coroutines."""

from __future__ import annotations

import inspect

from octop.infra.backend import compat


class _Raw:
    """Stands in for a legacy backend: every async method is the raw coroutine."""

    async def aread(self, *a, **k):
        return "raw-aread"

    async def awrite(self, *a, **k):
        return "raw-awrite"

    async def aedit(self, *a, **k):
        return "raw-aedit"

    async def agrep(self, *a, **k):
        return "raw-agrep"

    async def aglob(self, *a, **k):
        return "raw-aglob"

    async def aupload_files(self, *a, **k):
        return "raw-aupload"


ADAPTED = ("aread", "awrite", "aedit", "agrep", "aglob", "aupload_files")


def test_the_adapter_defines_the_async_names_itself():
    # __getattr__ would otherwise hand back the legacy coroutine, bypassing both
    # the result adaptation and the worker-loop affinity.
    for name in ADAPTED:
        assert name in vars(compat._LegacyProtocolBackend), name


def test_each_wrapper_runs_the_synchronous_adapted_method():
    source = inspect.getsource(compat._LegacyProtocolBackend)

    for name in ADAPTED:
        sync_name = name[1:]  # aread -> read
        assert f"asyncio.to_thread(self.{sync_name}" in source, name
