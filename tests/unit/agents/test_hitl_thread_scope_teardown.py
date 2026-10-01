"""``hitl_thread_scope`` teardown across asyncio tasks.

A streamed reply opens the scope inside an async generator, so ``ContextVar.set()``
runs in the context of whichever task drives ``__anext__``.  Abandoned streams are
finalized from a different task, and ``Token.reset()`` rejects a token created in
another context — see ``contextlib._GeneratorContextManager.__exit__``.
"""

from __future__ import annotations

import asyncio

from octop.infra.agents.security.hitl_session import (
    current_hitl_thread_id,
    hitl_thread_scope,
)


async def test_scope_teardown_from_another_task_does_not_raise():
    seen: list[object] = []

    async def agen():
        with hitl_thread_scope("thr_A"):
            seen.append(current_hitl_thread_id())
            yield 1
            seen.append("AFTER_YIELD")

    stream = agen()
    # The first ``__anext__`` binds the contextvar in *this* task's context.
    seen.append(await asyncio.create_task(stream.__anext__()))
    # Finalization happens elsewhere, as it does for an abandoned SSE stream.
    await asyncio.create_task(stream.aclose())

    assert seen == ["thr_A", 1]
