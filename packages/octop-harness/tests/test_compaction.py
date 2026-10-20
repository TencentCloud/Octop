"""Tests for forced conversation compaction."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, NonCallableMagicMock, patch

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage

from octop_harness.backends import resolve_backend
from octop_harness.compaction import (
    FORCE_KEEP_MESSAGES,
    MIN_EFFECTIVE_MESSAGES,
    CompactResult,
    display_offload_path,
    force_compact_thread,
)
from octop_harness.context_usage import conversation_tokens_from_messages, estimate_tokens
from octop_harness.middleware.memory_recall import replay_recall_snapshots, stamp_recall_snapshot


def _long_thread(n: int = 12) -> list:
    msgs: list = []
    for i in range(n):
        msgs.append(HumanMessage(content=f"user-{i} " + ("x" * 40)))
        msgs.append(AIMessage(content=f"asst-{i} " + ("y" * 40)))
    return msgs


@pytest.mark.asyncio
async def test_force_compact_nothing_when_too_short() -> None:
    graph = MagicMock()
    graph.aget_state = AsyncMock(return_value=SimpleNamespace(values={"messages": [HumanMessage(content="hi")]}))
    result = await force_compact_thread(
        graph=graph,
        backend=MagicMock(),
        model=MagicMock(profile={"max_input_tokens": 128_000}),
        thread_id="thr_x",
    )
    assert result.ok is False
    assert result.reason == "nothing_to_compact"
    graph.aupdate_state.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("recall", ["", "remember this detail " * 100])
async def test_force_compact_updates_summarization_event(recall: str) -> None:
    messages = _long_thread(8)
    if recall:
        messages[0] = stamp_recall_snapshot(messages[0], recall)
    graph = MagicMock()
    graph.aget_state = AsyncMock(
        return_value=SimpleNamespace(values={"messages": messages, "_summarization_event": None})
    )
    graph.aupdate_state = AsyncMock()

    model = MagicMock()
    model.profile = {"max_input_tokens": 8_000}
    model.ainvoke = AsyncMock(return_value=AIMessage(content="SUMMARY"))

    backend = MagicMock()
    backend.download_files = MagicMock(return_value=[SimpleNamespace(content=None, error="missing")])
    backend.write = MagicMock(return_value=SimpleNamespace(error=None))
    backend.edit = MagicMock(return_value=SimpleNamespace(error=None))

    with patch("octop_harness.compaction._build_force_summarization_middleware") as build_mw:
        mw = MagicMock()
        mw._apply_event_to_messages = MagicMock(side_effect=lambda msgs, _ev: list(msgs))
        # Keep last 6 → cutoff leaves many to summarize
        cutoff = len(messages) - FORCE_KEEP_MESSAGES
        mw._determine_cutoff_index = MagicMock(return_value=cutoff)
        mw._partition_messages = MagicMock(return_value=(messages[:cutoff], messages[cutoff:]))
        mw._aoffload_inline_media = AsyncMock(return_value=(messages[:cutoff], 0))
        mw._aoffload_to_backend = AsyncMock(return_value="/tmp/ws/conversation_history/thr_x.md")
        mw._acreate_summary = AsyncMock(return_value="SUMMARY TEXT")
        mw._build_new_messages_with_path = MagicMock(
            return_value=[
                HumanMessage(
                    content="summary",
                    additional_kwargs={"lc_source": "summarization"},
                )
            ]
        )
        mw._compute_state_cutoff = MagicMock(return_value=cutoff)
        build_mw.return_value = mw

        result = await force_compact_thread(
            graph=graph,
            backend=backend,
            model=model,
            thread_id="thr_x",
            model_ref="p/kimi",
        )

    assert result.ok is True
    assert result.summarized_count == cutoff
    assert result.preserved_count == FORCE_KEEP_MESSAGES
    assert result.file_path and result.file_path.endswith("thr_x.md")
    assert result.display_path == "conversation_history/thr_x.md"
    mw._acreate_summary.assert_awaited_once()
    # Summary model is the force MW built with turn *model*
    assert build_mw.call_args.args[0] is model
    graph.aupdate_state.assert_awaited_once()
    args, _kwargs = graph.aupdate_state.await_args
    assert args[0]["configurable"]["thread_id"] == "thr_x"
    assert args[0]["configurable"]["model"] == "p/kimi"
    assert args[1]["_summarization_event"]["cutoff_index"] == cutoff
    assert args[1]["_summarization_session_id"].startswith("session_")
    # Offloaded history minus the summary — what a stale context snapshot
    # should shed, since compaction makes no model call of its own.
    expected = conversation_tokens_from_messages(replay_recall_snapshots(messages[:cutoff])) - estimate_tokens(
        "summary"
    )
    if recall:
        assert expected > conversation_tokens_from_messages(messages[:cutoff]) - estimate_tokens("summary")
    assert result.removed_tokens == expected > 0


@pytest.mark.asyncio
async def test_force_compact_uses_graph_backend_but_turn_model() -> None:
    messages = _long_thread(6)
    assert len(messages) >= MIN_EFFECTIVE_MESSAGES

    graph = MagicMock()
    graph.aget_state = AsyncMock(
        return_value=SimpleNamespace(values={"messages": messages, "_summarization_event": None})
    )
    graph.aupdate_state = AsyncMock()

    graph_mw = MagicMock()
    graph_mw.serialized_name = "SummarizationMiddleware"
    # Real MW stores a backend instance (not a factory callable).
    graph_backend = NonCallableMagicMock(name="graph-backend")
    graph_mw._backend = graph_backend
    graph_mw._apply_event_to_messages = MagicMock(side_effect=lambda msgs, _ev: list(msgs))

    turn_model = MagicMock(name="kimi")
    turn_model.profile = {"max_input_tokens": 131_072}

    with patch("octop_harness.compaction._build_force_summarization_middleware") as build_mw:
        force_mw = MagicMock()
        cutoff = len(messages) - FORCE_KEEP_MESSAGES
        force_mw._determine_cutoff_index = MagicMock(return_value=cutoff)
        force_mw._partition_messages = MagicMock(return_value=(messages[:cutoff], messages[cutoff:]))
        force_mw._aoffload_inline_media = AsyncMock(return_value=(messages[:cutoff], 0))
        force_mw._aoffload_to_backend = AsyncMock(return_value="/ws/conversation_history/t.md")
        force_mw._acreate_summary = AsyncMock(return_value="S")
        force_mw._build_new_messages_with_path = MagicMock(
            return_value=[
                HumanMessage(
                    content="summary",
                    additional_kwargs={"lc_source": "summarization"},
                )
            ]
        )
        force_mw._compute_state_cutoff = MagicMock(return_value=cutoff)
        build_mw.return_value = force_mw

        result = await force_compact_thread(
            graph=graph,
            backend=MagicMock(name="fallback-backend"),
            model=turn_model,
            thread_id="thr_x",
            model_ref="p/kimi",
            summarization_middleware=graph_mw,
        )

    assert result.ok is True
    # Built with turn model + graph backend (artifacts_root)
    assert build_mw.call_args.args[0] is turn_model
    assert build_mw.call_args.args[1] is graph_backend
    force_mw._acreate_summary.assert_awaited()


@pytest.mark.asyncio
async def test_force_compact_runs_offload_and_summary_concurrently() -> None:
    """History offload and summary LLM must overlap (not run strictly serial)."""
    import asyncio

    messages = _long_thread(6)
    graph = MagicMock()
    graph.aget_state = AsyncMock(return_value=SimpleNamespace(values={"messages": messages}))
    graph.aupdate_state = AsyncMock()

    offload_started = asyncio.Event()
    summary_started = asyncio.Event()
    both_seen = asyncio.Event()

    async def slow_offload(_backend: object, _msgs: object, _session_id: str) -> str:
        offload_started.set()
        await summary_started.wait()
        both_seen.set()
        return "/ws/conversation_history/t.md"

    async def slow_summary(_msgs: object) -> str:
        summary_started.set()
        await offload_started.wait()
        return "S"

    with patch("octop_harness.compaction._build_force_summarization_middleware") as build_mw:
        mw = MagicMock()
        cutoff = len(messages) - FORCE_KEEP_MESSAGES
        mw._apply_event_to_messages = MagicMock(side_effect=lambda msgs, _ev: list(msgs))
        mw._determine_cutoff_index = MagicMock(return_value=cutoff)
        mw._partition_messages = MagicMock(return_value=(messages[:cutoff], messages[cutoff:]))
        mw._aoffload_inline_media = AsyncMock(return_value=(messages[:cutoff], 0))
        mw._aoffload_to_backend = AsyncMock(side_effect=slow_offload)
        mw._acreate_summary = AsyncMock(side_effect=slow_summary)
        mw._build_new_messages_with_path = MagicMock(
            return_value=[
                HumanMessage(
                    content="summary",
                    additional_kwargs={"lc_source": "summarization"},
                )
            ]
        )
        mw._compute_state_cutoff = MagicMock(return_value=cutoff)
        build_mw.return_value = mw

        result = await asyncio.wait_for(
            force_compact_thread(
                graph=graph,
                backend=MagicMock(),
                model=MagicMock(profile={"max_input_tokens": 128_000}),
                thread_id="thr_x",
            ),
            timeout=2.0,
        )

    assert result.ok is True
    assert both_seen.is_set()


@pytest.mark.asyncio
async def test_force_compact_skips_missing_inline_media_helper() -> None:
    """Older deepagents without ``_aoffload_inline_media`` still compact."""
    messages = _long_thread(6)
    graph = MagicMock()
    graph.aget_state = AsyncMock(return_value=SimpleNamespace(values={"messages": messages}))
    graph.aupdate_state = AsyncMock()

    with patch("octop_harness.compaction._build_force_summarization_middleware") as build_mw:
        mw = MagicMock(
            spec=[
                "_apply_event_to_messages",
                "_determine_cutoff_index",
                "_partition_messages",
                "_aoffload_to_backend",
                "_acreate_summary",
                "_build_new_messages_with_path",
                "_compute_state_cutoff",
            ]
        )
        cutoff = len(messages) - FORCE_KEEP_MESSAGES
        mw._apply_event_to_messages = MagicMock(side_effect=lambda msgs, _ev: list(msgs))
        mw._determine_cutoff_index = MagicMock(return_value=cutoff)
        mw._partition_messages = MagicMock(return_value=(messages[:cutoff], messages[cutoff:]))
        mw._aoffload_to_backend = AsyncMock(return_value="/ws/h.md")
        mw._acreate_summary = AsyncMock(return_value="S")
        mw._build_new_messages_with_path = MagicMock(
            return_value=[
                HumanMessage(
                    content="summary",
                    additional_kwargs={"lc_source": "summarization"},
                )
            ]
        )
        mw._compute_state_cutoff = MagicMock(return_value=cutoff)
        build_mw.return_value = mw

        result = await force_compact_thread(
            graph=graph,
            backend=MagicMock(),
            model=MagicMock(profile={"max_input_tokens": 128_000}),
            thread_id="thr_x",
        )

    assert result.ok is True
    mw._acreate_summary.assert_awaited_once()


@pytest.mark.asyncio
async def test_force_compact_rejects_single_message_slice() -> None:
    # Exactly keep+1 effective messages → only 1 would be summarized → reject.
    messages = [HumanMessage(content=f"m{i}") for i in range(FORCE_KEEP_MESSAGES + 1)]
    graph = MagicMock()
    graph.aget_state = AsyncMock(return_value=SimpleNamespace(values={"messages": messages}))

    with patch("octop_harness.compaction._build_force_summarization_middleware") as build_mw:
        mw = MagicMock()
        mw._apply_event_to_messages = MagicMock(side_effect=lambda msgs, _ev: list(msgs))
        mw._determine_cutoff_index = MagicMock(return_value=1)
        mw._partition_messages = MagicMock(return_value=(messages[:1], messages[1:]))
        build_mw.return_value = mw

        result = await force_compact_thread(
            graph=graph,
            backend=MagicMock(),
            model=MagicMock(profile={"max_input_tokens": 128_000}),
            thread_id="thr_x",
        )

    assert result == CompactResult(ok=False, reason="nothing_to_compact")
    mw._acreate_summary.assert_not_called()


@pytest.mark.asyncio
async def test_force_compact_passes_session_id_to_offload() -> None:
    """deepagents ``_aoffload_to_backend`` requires ``session_id``."""
    messages = _long_thread(6)
    graph = MagicMock()
    graph.aget_state = AsyncMock(
        return_value=SimpleNamespace(
            values={
                "messages": messages,
                "_summarization_session_id": "session_existing",
            }
        )
    )
    graph.aupdate_state = AsyncMock()
    seen: list[str] = []

    async def offload(_backend: object, _msgs: object, session_id: str) -> str:
        seen.append(session_id)
        return f"/ws/conversation_history/{session_id}.md"

    with patch("octop_harness.compaction._build_force_summarization_middleware") as build_mw:
        mw = MagicMock()
        cutoff = len(messages) - FORCE_KEEP_MESSAGES
        mw._get_session_id = MagicMock(return_value="session_existing")
        mw._apply_event_to_messages = MagicMock(side_effect=lambda msgs, _ev: list(msgs))
        mw._determine_cutoff_index = MagicMock(return_value=cutoff)
        mw._partition_messages = MagicMock(return_value=(messages[:cutoff], messages[cutoff:]))
        mw._aoffload_inline_media = AsyncMock(return_value=(messages[:cutoff], 0))
        mw._aoffload_to_backend = offload
        mw._acreate_summary = AsyncMock(return_value="S")
        mw._build_new_messages_with_path = MagicMock(
            return_value=[
                HumanMessage(
                    content="summary",
                    additional_kwargs={"lc_source": "summarization"},
                )
            ]
        )
        mw._compute_state_cutoff = MagicMock(return_value=cutoff)
        build_mw.return_value = mw

        result = await force_compact_thread(
            graph=graph,
            backend=MagicMock(),
            model=MagicMock(profile={"max_input_tokens": 128_000}),
            thread_id="thr_x",
        )

    assert result.ok is True
    assert seen == ["session_existing"]
    assert result.file_path == "/ws/conversation_history/session_existing.md"
    assert result.display_path == "conversation_history/session_existing.md"
    update = graph.aupdate_state.await_args.args[1]
    assert update["_summarization_session_id"] == "session_existing"


def _workspace_backend(tmp_path):
    return resolve_backend(
        {"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": True},
        workspace_dir=tmp_path,
        system_files_path=".octop",
    )


class _SummaryFakeModel(FakeListChatModel):
    """FakeList that summarization middleware can invoke and bind."""

    def bind_tools(self, tools: object, **kwargs: object) -> _SummaryFakeModel:
        del tools, kwargs
        return self


def _summary_model(*texts: str) -> _SummaryFakeModel:
    model = _SummaryFakeModel(responses=list(texts))
    object.__setattr__(model, "profile", {"max_input_tokens": 128_000})
    return model


@pytest.mark.asyncio
async def test_force_compact_real_middleware_writes_history_file(tmp_path) -> None:
    """Real SummarizationMiddleware + filesystem backend must write session_*.md.

    This is the regression that mocked offload missed: deepagents requires
    ``session_id`` on ``_aoffload_to_backend``.
    """
    messages = _long_thread(8)
    graph = MagicMock()
    graph.aget_state = AsyncMock(return_value=SimpleNamespace(values={"messages": messages}))
    graph.aupdate_state = AsyncMock()

    result = await force_compact_thread(
        graph=graph,
        backend=_workspace_backend(tmp_path),
        model=_summary_model("SUMMARY"),
        thread_id="thr_real",
    )

    assert result.ok is True
    assert result.file_path
    sid = graph.aupdate_state.await_args.args[1]["_summarization_session_id"]
    assert sid.startswith("session_")
    assert result.display_path == f".octop/conversation_history/{sid}.md"
    hist = tmp_path / ".octop" / "conversation_history" / f"{sid}.md"
    assert hist.is_file()
    text = hist.read_text(encoding="utf-8")
    assert "## Summarized at" in text
    assert "user-0" in text


@pytest.mark.asyncio
async def test_force_compact_second_pass_appends_same_session_file(tmp_path) -> None:
    """A later /compact must append the same session history file."""
    messages = _long_thread(8)
    state: dict = {"messages": messages}
    graph = MagicMock()
    graph.aget_state = AsyncMock(side_effect=lambda _cfg: SimpleNamespace(values=dict(state)))

    async def _store(_cfg: object, update: dict) -> None:
        state.update(update)

    graph.aupdate_state = AsyncMock(side_effect=_store)
    backend = _workspace_backend(tmp_path)
    model = _summary_model("SUMMARY-1", "SUMMARY-2")

    first = await force_compact_thread(graph=graph, backend=backend, model=model, thread_id="thr_real")
    assert first.ok is True
    sid = state["_summarization_session_id"]
    hist = tmp_path / ".octop" / "conversation_history" / f"{sid}.md"
    first_text = hist.read_text(encoding="utf-8")
    assert first_text.count("## Summarized at") == 1

    # Grow the raw transcript so a second force compact is eligible.
    state["messages"] = list(state["messages"]) + _long_thread(6)

    second = await force_compact_thread(graph=graph, backend=backend, model=model, thread_id="thr_real")
    assert second.ok is True
    assert state["_summarization_session_id"] == sid
    assert second.file_path == first.file_path
    assert first.display_path == second.display_path == f".octop/conversation_history/{sid}.md"
    second_text = hist.read_text(encoding="utf-8")
    assert second_text.startswith(first_text)
    assert second_text.count("## Summarized at") == 2


@pytest.mark.parametrize(
    ("raw", "session_id", "expected"),
    [
        (
            r"C:\Users\wally\.octop\workspaces\X\.octop\conversation_history\session_ab.md",
            "session_ab",
            ".octop/conversation_history/session_ab.md",
        ),
        (
            r"\\?\C:\Users\wally\.octop\workspaces\X\.octop\conversation_history\session_ab.md",
            "session_ab",
            ".octop/conversation_history/session_ab.md",
        ),
        (
            r"\\server\share\.octop\conversation_history\session_ab.md",
            "session_ab",
            ".octop/conversation_history/session_ab.md",
        ),
        (
            "/home/wally/.octop/workspaces/X/.octop/conversation_history/session_ab.md",
            "session_ab",
            ".octop/conversation_history/session_ab.md",
        ),
        (
            "/Users/wally/.octop/workspaces/X/.octop/conversation_history/session_ab.md",
            "session_ab",
            ".octop/conversation_history/session_ab.md",
        ),
        (
            r"D:\data\conversation_history\session_ab.md",
            "session_ab",
            "conversation_history/session_ab.md",
        ),
        (
            "C:/Users/wally/.octop/conversation_history/session_ab.md",
            "session_ab",
            ".octop/conversation_history/session_ab.md",
        ),
        (
            "/conversation_history/session_ab.md",
            "session_ab",
            "conversation_history/session_ab.md",
        ),
        (None, "session_ab", "conversation_history/session_ab.md"),
    ],
)
def test_display_offload_path_is_posix_on_every_os(raw: str | None, session_id: str, expected: str) -> None:
    got = display_offload_path(raw, session_id)
    assert got == expected
    assert "\\" not in got
    assert not (len(got) >= 2 and got[1] == ":")


@pytest.mark.asyncio
async def test_force_compact_offload_none_does_not_update_state() -> None:
    messages = _long_thread(6)
    graph = MagicMock()
    graph.aget_state = AsyncMock(return_value=SimpleNamespace(values={"messages": messages}))
    graph.aupdate_state = AsyncMock()

    with patch("octop_harness.compaction._build_force_summarization_middleware") as build_mw:
        mw = MagicMock()
        cutoff = len(messages) - FORCE_KEEP_MESSAGES
        mw._apply_event_to_messages = MagicMock(side_effect=lambda msgs, _ev: list(msgs))
        mw._determine_cutoff_index = MagicMock(return_value=cutoff)
        mw._partition_messages = MagicMock(return_value=(messages[:cutoff], messages[cutoff:]))
        mw._aoffload_inline_media = AsyncMock(return_value=(messages[:cutoff], 0))
        mw._aoffload_to_backend = AsyncMock(return_value=None)
        mw._acreate_summary = AsyncMock(return_value="S")
        build_mw.return_value = mw

        result = await force_compact_thread(
            graph=graph,
            backend=MagicMock(),
            model=MagicMock(profile={"max_input_tokens": 128_000}),
            thread_id="thr_x",
        )

    assert result.ok is False
    assert result.reason == "error"
    assert result.error == "history offload failed"
    graph.aupdate_state.assert_not_called()


@pytest.mark.asyncio
async def test_force_compact_reuses_graph_mw_and_restores_keep(tmp_path) -> None:
    from deepagents.middleware.summarization import (
        SummarizationMiddleware,
        compute_summarization_defaults,
    )

    backend = _workspace_backend(tmp_path)
    model = _summary_model("SUMMARY")
    defaults = compute_summarization_defaults(model)
    graph_mw = SummarizationMiddleware(
        model=model,
        backend=backend,
        trigger=defaults["trigger"],
        keep=defaults["keep"],
    )
    original_keep = graph_mw._lc_helper.keep
    messages = _long_thread(8)
    graph = MagicMock()
    graph.aget_state = AsyncMock(return_value=SimpleNamespace(values={"messages": messages}))
    graph.aupdate_state = AsyncMock()

    with patch("octop_harness.compaction._build_force_summarization_middleware") as build_mw:
        result = await force_compact_thread(
            graph=graph,
            backend=backend,
            model=model,
            thread_id="thr_real",
            summarization_middleware=graph_mw,
        )

    assert result.ok is True
    build_mw.assert_not_called()
    assert graph_mw._lc_helper.keep == original_keep
    sid = graph.aupdate_state.await_args.args[1]["_summarization_session_id"]
    assert result.display_path == f".octop/conversation_history/{sid}.md"
