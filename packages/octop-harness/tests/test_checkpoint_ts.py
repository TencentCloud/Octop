"""Tests for CheckpointTsMiddleware write-time stamps."""

from __future__ import annotations

from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage

from octop_harness.messages import CHECKPOINT_TS_KEY
from octop_harness.middleware.checkpoint_ts import CheckpointTsMiddleware, stamp_missing_checkpoint_ts


class TestStampMissingCheckpointTs:
    def test_stamps_from_start_only(self) -> None:
        old = HumanMessage(content="old", id="m-old")
        new = HumanMessage(content="new", id="m-new")
        stamped = stamp_missing_checkpoint_ts([old, new], start=1, now_ms=1_700_000_000_000)
        assert len(stamped) == 1
        assert stamped[0].id == "m-new"
        assert stamped[0].additional_kwargs[CHECKPOINT_TS_KEY] == 1_700_000_000_000

    def test_skips_already_stamped(self) -> None:
        msg = HumanMessage(
            content="hi",
            id="m1",
            additional_kwargs={CHECKPOINT_TS_KEY: 123},
        )
        assert stamp_missing_checkpoint_ts([msg], now_ms=999) == []


class TestCheckpointTsMiddleware:
    def test_before_model_stamps_trailing_human(self) -> None:
        mw = CheckpointTsMiddleware()
        prior = HumanMessage(
            content="prior",
            id="m-prior",
            # deliberately unstamped — must NOT be rewritten to "now"
        )
        user = HumanMessage(content="hi", id="m-user")
        update = mw.before_model({"messages": [prior, user]}, MagicMock())
        assert update is not None
        stamped_ids = {m.id for m in update["messages"]}
        assert stamped_ids == {"m-user"}
        assert CHECKPOINT_TS_KEY in update["messages"][0].additional_kwargs

    def test_after_model_stamps_new_assistant_only(self) -> None:
        mw = CheckpointTsMiddleware()
        user = HumanMessage(
            content="hi",
            id="m-user",
            additional_kwargs={CHECKPOINT_TS_KEY: 100},
        )
        ai = AIMessage(content="yo", id="m-ai")
        update = mw.after_model({"messages": [user, ai]}, MagicMock())
        assert update is not None
        assert [m.id for m in update["messages"]] == ["m-ai"]
        assert CHECKPOINT_TS_KEY in update["messages"][0].additional_kwargs

    def test_after_model_does_not_rewrite_prior_unstamped(self) -> None:
        mw = CheckpointTsMiddleware()
        prior = HumanMessage(content="old", id="m-old")
        user = HumanMessage(
            content="hi",
            id="m-user",
            additional_kwargs={CHECKPOINT_TS_KEY: 100},
        )
        ai = AIMessage(content="yo", id="m-ai")
        update = mw.after_model({"messages": [prior, user, ai]}, MagicMock())
        assert update is not None
        assert [m.id for m in update["messages"]] == ["m-ai"]
