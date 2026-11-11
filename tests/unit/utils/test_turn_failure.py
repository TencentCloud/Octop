from __future__ import annotations

import logging

from langchain_core.messages import ToolMessage

from octop.infra.utils.turn_failure import (
    current_turn_model,
    iter_failed_tool_results,
    log_failed_tool_results,
    log_turn_failure,
    turn_model_scope,
)


def test_log_turn_failure_includes_kind_and_ids(caplog: logging.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR, logger="octop.infra.utils.turn_failure"):
        log_turn_failure(
            "model_retry",
            detail="Error code: 422 Check open ai req parameter error",
            agent_id="ag_1",
            thread_id="th_9",
            model="qwen",
            exc=RuntimeError("422"),
            level=logging.ERROR,
        )
    assert "turn failure kind=model_retry" in caplog.text
    assert "agent=ag_1" in caplog.text
    assert "thread=th_9" in caplog.text
    assert "model=qwen" in caplog.text
    assert "Check open ai req parameter error" in caplog.text


def test_iter_failed_tool_results_reads_status_error() -> None:
    chunk = {
        "type": "tool_result",
        "name": "read_file",
        "messages": [
            {"name": "read_file", "status": "error", "content": "File not found"},
            {"name": "read_file", "status": "success", "content": "ok"},
        ],
    }
    rows = iter_failed_tool_results(chunk)
    assert len(rows) == 1
    assert rows[0][:2] == ("read_file", "File not found")
    assert iter_failed_tool_results({"type": "token", "content": "x"}) == []


def test_iter_failed_tool_results_accepts_tool_message() -> None:
    chunk = {
        "type": "tool_result",
        "messages": [
            ToolMessage(
                content="MCP timeout",
                tool_call_id="c1",
                name="web_fetch",
                status="error",
            )
        ],
    }
    rows = iter_failed_tool_results(chunk)
    assert rows[0][:2] == ("web_fetch", "MCP timeout")
    assert rows[0][2] == "id:c1"


def test_log_failed_tool_results_is_warning(caplog: logging.LogCaptureFixture) -> None:
    chunk = {
        "type": "tool_result",
        "messages": [{"name": "ls", "status": "error", "content": "permission denied"}],
    }
    with caplog.at_level(logging.WARNING, logger="octop.infra.utils.turn_failure"):
        log_failed_tool_results(chunk, agent_id="ag_2", thread_id="th_3")
    assert "turn failure kind=tool" in caplog.text
    assert "agent=ag_2" in caplog.text
    assert "tool=ls" in caplog.text
    assert "permission denied" in caplog.text
    assert not any(r.levelno >= logging.ERROR for r in caplog.records)


def test_log_failed_tool_results_skips_replay_and_history(
    caplog: logging.LogCaptureFixture,
) -> None:
    chunk = {
        "type": "tool_result",
        "messages": [
            {
                "name": "read_file",
                "status": "error",
                "tool_call_id": "c1",
                "content": "File not found",
            }
        ],
    }
    seen: set[str] = set()
    with caplog.at_level(logging.WARNING, logger="octop.infra.utils.turn_failure"):
        log_failed_tool_results(chunk, agent_id="ag", seen=seen, live=False)
        log_failed_tool_results(chunk, agent_id="ag", seen=seen, live=True)
        log_failed_tool_results(chunk, agent_id="ag", seen=seen, live=True)
    assert caplog.text.count("turn failure kind=tool") == 1


def test_turn_model_scope_binds_current_label() -> None:
    assert current_turn_model() == ""
    with turn_model_scope("provider/qwen"):
        assert current_turn_model() == "provider/qwen"
    assert current_turn_model() == ""
