"""Tests for octop_browser.cli — action dispatch + output formatting."""

from __future__ import annotations

import json
from typing import Any

import pytest

from octop_browser import cli as cli_mod
from octop_browser.models import ActionMetrics, ToolResult


def _ok(content: Any = "ok", action: str = "test", metadata=None) -> ToolResult:
    return ToolResult(
        success=True,
        content=content,
        metrics=ActionMetrics(
            action=action, duration_ms=1, dom_nodes_scanned=0, estimated_tokens=0
        ),
        metadata=metadata,
    )


def _err(error: str = "boom", action: str = "test") -> ToolResult:
    return ToolResult(
        success=False,
        content="",
        error=error,
        metrics=ActionMetrics(
            action=action, duration_ms=1, dom_nodes_scanned=0, estimated_tokens=0
        ),
    )


@pytest.fixture
def capture_browser_tool(monkeypatch):
    """Replace browser_tool with a recording stub returning a configurable result."""
    calls: list[dict[str, Any]] = []
    state: dict[str, ToolResult] = {"result": _ok()}

    async def fake(action: str, profile: str = "default", mode=None, **kwargs):
        calls.append(
            {"action": action, "profile": profile, "mode": mode, "kwargs": kwargs}
        )
        return state["result"]

    monkeypatch.setattr(cli_mod, "browser_tool", fake)
    return calls, state


# ---------------------------------------------------------------------------
# Action dispatch — argument translation & profile/mode propagation
# ---------------------------------------------------------------------------


def test_navigate_dispatches_url_and_profile(capture_browser_tool):
    calls, _ = capture_browser_tool
    rc = cli_mod.main(["navigate", "https://example.com", "--profile", "work"])
    assert rc == 0
    assert calls == [
        {
            "action": "navigate",
            "profile": "work",
            "mode": None,
            "kwargs": {"url": "https://example.com"},
        }
    ]


def test_dom_tree_translates_dash_to_underscore(capture_browser_tool):
    calls, _ = capture_browser_tool
    cli_mod.main(["dom-tree", "--level", "minimal"])
    assert calls[0]["action"] == "dom_tree"
    assert calls[0]["kwargs"] == {"level": "minimal"}


def test_screenshot_optional_flags(capture_browser_tool):
    calls, _ = capture_browser_tool
    cli_mod.main(
        [
            "screenshot",
            "--full-page",
            "--path",
            "/tmp/p.png",
            "--profile",
            "github",
        ]
    )
    assert calls[0] == {
        "action": "screenshot",
        "profile": "github",
        "mode": None,
        "kwargs": {"full_page": True, "path": "/tmp/p.png"},
    }


def test_screenshot_no_flags_means_no_kwargs(capture_browser_tool):
    calls, _ = capture_browser_tool
    cli_mod.main(["screenshot"])
    assert calls[0]["kwargs"] == {}


def test_click_ref_branch(capture_browser_tool):
    calls, _ = capture_browser_tool
    cli_mod.main(["click", "--ref", "btn_2"])
    assert calls[0]["kwargs"] == {"ref": "btn_2"}


def test_click_xy_branch(capture_browser_tool):
    calls, _ = capture_browser_tool
    cli_mod.main(["click", "--xy", "100", "200"])
    assert calls[0]["kwargs"] == {"x": 100, "y": 200}


def test_click_requires_target(capsys):
    """--ref / --selector / --xy are mutually-exclusive but one is required."""
    with pytest.raises(SystemExit):
        cli_mod.main(["click"])


def test_type_with_optional_ref(capture_browser_tool):
    calls, _ = capture_browser_tool
    cli_mod.main(["type", "hello", "--ref", "inp_1"])
    assert calls[0]["action"] == "type"
    assert calls[0]["kwargs"] == {"text": "hello", "ref": "inp_1"}


def test_eval_js_dispatch(capture_browser_tool):
    calls, _ = capture_browser_tool
    cli_mod.main(["eval-js", "1+1"])
    assert calls[0]["action"] == "eval_js"
    assert calls[0]["kwargs"] == {"expression": "1+1"}


def test_no_arg_actions_dispatch_with_empty_kwargs(capture_browser_tool):
    calls, _ = capture_browser_tool
    for cmd in ("go-back", "go-forward", "reload", "list-tabs", "close-session"):
        calls.clear()
        cli_mod.main([cmd])
        assert calls[0]["kwargs"] == {}


def test_tab_subcommands(capture_browser_tool):
    calls, _ = capture_browser_tool
    cli_mod.main(["new-tab", "--url", "https://a.com"])
    assert calls[-1]["action"] == "new_tab"
    assert calls[-1]["kwargs"] == {"url": "https://a.com"}

    cli_mod.main(["switch-tab", "tgt-123"])
    assert calls[-1]["action"] == "switch_tab"
    assert calls[-1]["kwargs"] == {"tab_id": "tgt-123"}

    cli_mod.main(["close-tab", "--tab-id", "tgt-123"])
    assert calls[-1]["action"] == "close_tab"
    assert calls[-1]["kwargs"] == {"tab_id": "tgt-123"}


def test_mode_flag_propagates(capture_browser_tool):
    calls, _ = capture_browser_tool
    cli_mod.main(["navigate", "https://e.com", "--headless"])
    assert calls[0]["mode"] == "headless"

    calls.clear()
    cli_mod.main(["navigate", "https://e.com", "--headed"])
    assert calls[0]["mode"] == "headed"


def test_close_session_does_not_accept_mode_flag(capsys):
    """close-session is a teardown; mode flags are nonsensical there."""
    with pytest.raises(SystemExit):
        cli_mod.main(["close-session", "--headless"])


# ---------------------------------------------------------------------------
# Top-level help and metadata
# ---------------------------------------------------------------------------


def test_top_level_help_groups_commands_and_shows_examples(capsys):
    with pytest.raises(SystemExit) as exc_info:
        cli_mod.main(["--help"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert "commands:" in captured.out
    assert "Run '<command> --help'" in captured.out
    assert "Examples:" in captured.out
    assert "octop-browser navigate https://example.com --profile work" in captured.out
    assert captured.err == ""


def test_version_prints_package_name_and_version(capsys):
    with pytest.raises(SystemExit) as exc_info:
        cli_mod.main(["--version"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert captured.out.startswith("octop-browser ")
    assert captured.err == ""


def test_install_help_explains_playwright_bootstrap(capsys):
    with pytest.raises(SystemExit) as exc_info:
        cli_mod.main(["install-browser", "--help"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    help_text = " ".join(captured.out.split())
    assert "managed Chromium binary" in help_text
    assert "not used to drive the browser" in help_text
    assert captured.err == ""


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def test_default_output_is_content(capture_browser_tool, capsys):
    _, state = capture_browser_tool
    state["result"] = _ok(content="hello world")
    rc = cli_mod.main(["navigate", "https://e.com"])
    out = capsys.readouterr().out.strip()
    assert rc == 0
    assert out == "hello world"


def test_default_output_for_dict_content_is_json(capture_browser_tool, capsys):
    _, state = capture_browser_tool
    state["result"] = _ok(content={"k": "v"})
    cli_mod.main(["dom-tree"])
    out = capsys.readouterr().out.strip()
    assert json.loads(out) == {"k": "v"}


def test_json_flag_returns_full_payload(capture_browser_tool, capsys):
    _, state = capture_browser_tool
    state["result"] = _ok(content="ok", metadata={"width": 1440})
    cli_mod.main(["screenshot", "--json"])
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert payload["success"] is True
    assert payload["content"] == "ok"
    assert payload["metadata"] == {"width": 1440}
    assert payload["metrics"]["action"] == "test"


def test_error_goes_to_stderr_with_nonzero_exit(capture_browser_tool, capsys):
    _, state = capture_browser_tool
    state["result"] = _err(error="page not found")
    rc = cli_mod.main(["navigate", "https://nope"])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert "page not found" in captured.err


def test_error_with_json_returns_full_payload_on_stderr(capture_browser_tool, capsys):
    _, state = capture_browser_tool
    state["result"] = _err(error="boom")
    rc = cli_mod.main(["navigate", "https://nope", "--json"])
    captured = capsys.readouterr()
    assert rc == 1
    payload = json.loads(captured.err.strip())
    assert payload["success"] is False
    assert payload["error"] == "boom"


def test_fill_accepts_selector_target(capture_browser_tool):
    calls, _ = capture_browser_tool
    cli_mod.main(["fill", "hello", "--selector", "#query"])
    assert calls[0]["action"] == "fill"
    assert calls[0]["kwargs"] == {"text": "hello", "selector": "#query"}


def test_type_accepts_selector_target(capture_browser_tool):
    calls, _ = capture_browser_tool
    cli_mod.main(["type", "hello", "--selector", "#query"])
    assert calls[0]["action"] == "type"
    assert calls[0]["kwargs"] == {"text": "hello", "selector": "#query"}


def test_record_show_dispatches_summary(monkeypatch, capsys):
    class FakeStore:
        def recording_summary(self, recording_id):
            assert recording_id == "rec_x"
            return {"recordingId": recording_id, "stepsPath": "/tmp/steps.json"}

    monkeypatch.setattr(cli_mod, "RecordingStore", FakeStore)

    rc = cli_mod.main(["record", "show", "rec_x", "--json"])

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["ok"] is True
    assert out["recordingId"] == "rec_x"
    assert out["stepsPath"] == "/tmp/steps.json"
