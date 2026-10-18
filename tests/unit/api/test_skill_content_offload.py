"""Reading the generated skill content must not run on the event loop."""

from __future__ import annotations

import inspect

from octop.api.routers.browser import record_replay as record_replay_router


def test_skill_content_read_is_offloaded():
    source = inspect.getsource(record_replay_router.get_skill_content)

    # The manifest lookup and the draft.skill.md read are blocking file I/O, so the
    # handler must run them on a worker thread.
    assert "await asyncio.to_thread(_read_skill)" in source
    assert "def _read_skill()" in source
    assert 'skill_path.read_text(encoding="utf-8")' in source


def test_the_blocking_calls_live_inside_the_inner_function():
    source = inspect.getsource(record_replay_router.get_skill_content)
    inner = source.split("def _read_skill()", 1)[1]

    assert "skill_path.read_text(" in inner
    assert "_require_owned_recording(" in inner
