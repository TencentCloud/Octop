import json
from pathlib import Path

import pytest

from octop_browser.models import ActionMetrics, ToolResult
from octop_browser.record.models import (
    RecordingManifest,
    SemanticStep,
    StepsDocument,
)
from octop_browser.record.replay import ReplayRunner
from octop_browser.record.settings import RecordReplaySettings
from octop_browser.record.store import RecordingStore


def _result(
    action: str, success: bool = True, content="", error: str | None = None
) -> ToolResult:
    return ToolResult(
        success=success,
        content=content,
        error=error,
        metrics=ActionMetrics(
            action=action, duration_ms=1, dom_nodes_scanned=0, estimated_tokens=0
        ),
    )


def _store_with_steps(
    tmp_path: Path, recording_id: str, steps: StepsDocument
) -> RecordingStore:
    store = RecordingStore(RecordReplaySettings(base_dir=tmp_path))
    store.create(RecordingManifest(recordingId=recording_id, createdAt="now"))
    store.write_steps(recording_id, steps)
    return store


@pytest.mark.asyncio
async def test_replay_fails_empty_steps_instead_of_false_pass(tmp_path):
    store = _store_with_steps(
        tmp_path,
        "rec_empty",
        StepsDocument(recordingId="rec_empty", startUrl="", steps=[]),
    )

    report = await ReplayRunner(store).run("rec_empty", profile="demo")

    assert report["status"] == "failed"
    assert report["error"] == "Recording has no replayable steps"
    assert report["stepsLoaded"] == 0


@pytest.mark.asyncio
async def test_replay_runs_document_level_verification(monkeypatch, tmp_path):
    calls: list[tuple[str, dict]] = []

    async def fake_browser_tool(action: str, **kwargs):
        calls.append((action, kwargs))
        return _result(action, content="ok")

    monkeypatch.setattr("octop_browser.record.replay.browser_tool", fake_browser_tool)
    store = _store_with_steps(
        tmp_path,
        "rec_verify",
        StepsDocument(
            recordingId="rec_verify",
            startUrl="https://example.com/start",
            steps=[
                SemanticStep(
                    id="step_001", kind="open", url="https://example.com/start"
                )
            ],
            verification=[{"type": "url_contains", "value": "/done"}],
        ),
    )

    report = await ReplayRunner(store).run("rec_verify", profile="demo")

    assert report["status"] == "passed"
    assert calls[-1] == (
        "wait",
        {"profile": "demo", "url_contains": "/done", "timeout_ms": 10000},
    )
    assert report["verification"] == [
        {"type": "url_contains", "value": "/done", "status": "passed"}
    ]


@pytest.mark.asyncio
async def test_replay_switches_to_recorded_target_before_targeted_actions(
    monkeypatch, tmp_path
):
    calls: list[tuple[str, dict]] = []
    dom = json.dumps(
        {
            "elements": [
                {
                    "ref": "btn_0",
                    "role": "button",
                    "accessibleName": "Go",
                    "selectorCandidates": ["#go"],
                }
            ]
        }
    )

    async def fake_browser_tool(action: str, **kwargs):
        calls.append((action, kwargs))
        if action == "new_tab":
            return _result(action, content="runtime_tab_b")
        if action == "dom_tree":
            return _result(action, content=dom)
        return _result(action, content="ok")

    monkeypatch.setattr("octop_browser.record.replay.browser_tool", fake_browser_tool)
    store = _store_with_steps(
        tmp_path,
        "rec_tabs",
        StepsDocument(
            recordingId="rec_tabs",
            steps=[
                SemanticStep(
                    id="step_001",
                    kind="open",
                    url="https://example.com/a",
                    target={"targetId": "tab_a"},
                ),
                SemanticStep(
                    id="step_002",
                    kind="new_tab",
                    url="https://example.com/b",
                    target={"targetId": "tab_b"},
                ),
                SemanticStep(
                    id="step_003",
                    kind="click",
                    target={
                        "targetId": "tab_b",
                        "role": "button",
                        "name": "Go",
                        "selectorCandidates": ["#go"],
                    },
                ),
            ],
        ),
    )

    report = await ReplayRunner(store).run("rec_tabs", profile="demo")

    assert report["status"] == "passed"
    assert ("switch_tab", {"profile": "demo", "tab_id": "runtime_tab_b"}) in calls
    switch_index = calls.index(
        ("switch_tab", {"profile": "demo", "tab_id": "runtime_tab_b"})
    )
    dom_index = next(i for i, c in enumerate(calls) if c[0] == "dom_tree")
    assert switch_index < dom_index


@pytest.mark.asyncio
async def test_replay_writes_failure_diagnostics_when_target_cannot_be_matched(
    monkeypatch, tmp_path
):
    async def fake_browser_tool(action: str, **kwargs):
        if action == "dom_tree":
            return _result(
                action,
                content=json.dumps({"url": "https://example.com", "elements": []}),
            )
        if action == "screenshot":
            path = tmp_path / "failure.png"
            path.write_bytes(b"png")
            return _result(action, content=str(path))
        return _result(action, content="ok")

    monkeypatch.setattr("octop_browser.record.replay.browser_tool", fake_browser_tool)
    store = _store_with_steps(
        tmp_path,
        "rec_fail",
        StepsDocument(
            recordingId="rec_fail",
            steps=[
                SemanticStep(
                    id="step_001",
                    kind="click",
                    target={"role": "button", "name": "Missing"},
                )
            ],
        ),
    )

    report = await ReplayRunner(store).run("rec_fail", profile="demo")

    assert report["status"] == "failed"
    assert "failureArtifacts" in report
    artifacts = report["failureArtifacts"]
    assert Path(artifacts["domSnapshotPath"]).exists()
    assert Path(artifacts["screenshotPath"]).exists()


@pytest.mark.asyncio
async def test_replay_rewrites_baidu_search_url_when_query_input_changes(
    monkeypatch, tmp_path
):
    calls: list[tuple[str, dict]] = []

    async def fake_browser_tool(action: str, **kwargs):
        calls.append((action, kwargs))
        return _result(action, content="ok")

    monkeypatch.setattr("octop_browser.record.replay.browser_tool", fake_browser_tool)
    store = _store_with_steps(
        tmp_path,
        "rec_baidu",
        StepsDocument(
            recordingId="rec_baidu",
            steps=[
                SemanticStep(id="step_001", kind="open", url="https://www.baidu.com/"),
                SemanticStep(
                    id="step_002",
                    kind="navigate",
                    url="https://www.baidu.com/s?wd=%E4%BB%8A%E5%A4%A9%E5%8C%97%E4%BA%AC%E5%A4%A9%E6%B0%94&ie=utf-8",
                ),
            ],
        ),
    )

    report = await ReplayRunner(store).run(
        "rec_baidu", profile="demo", inputs={"query": "上海天气"}
    )

    assert report["status"] == "passed"
    assert calls[1] == (
        "navigate",
        {
            "profile": "demo",
            "url": "https://www.baidu.com/s?wd=%E4%B8%8A%E6%B5%B7%E5%A4%A9%E6%B0%94&ie=utf-8",
        },
    )


@pytest.mark.asyncio
async def test_replay_runs_select_step(monkeypatch, tmp_path):
    calls: list[tuple[str, dict]] = []
    dom = json.dumps(
        {
            "elements": [
                {
                    "ref": "sel_0",
                    "tag": "select",
                    "role": "combobox",
                    "accessibleName": "Country",
                    "selectorCandidates": ['select[name="country"]'],
                }
            ]
        }
    )

    async def fake_browser_tool(action: str, **kwargs):
        calls.append((action, kwargs))
        if action == "dom_tree":
            return _result(action, content=dom)
        return _result(action, content="ok")

    monkeypatch.setattr("octop_browser.record.replay.browser_tool", fake_browser_tool)
    store = _store_with_steps(
        tmp_path,
        "rec_select",
        StepsDocument(
            recordingId="rec_select",
            steps=[
                SemanticStep(
                    id="step_001",
                    kind="select",
                    target={
                        "role": "combobox",
                        "name": "Country",
                        "selectorCandidates": ['select[name="country"]'],
                    },
                    value="{{country}}",
                )
            ],
        ),
    )

    report = await ReplayRunner(store).run(
        "rec_select", profile="demo", inputs={"country": "CN"}
    )

    assert report["status"] == "passed"
    assert ("select", {"profile": "demo", "ref": "sel_0", "value": "CN"}) in calls


@pytest.mark.asyncio
async def test_replay_runs_set_checked_via_selector_fallback(monkeypatch, tmp_path):
    calls: list[tuple[str, dict]] = []

    async def fake_browser_tool(action: str, **kwargs):
        calls.append((action, kwargs))
        if action == "dom_tree":
            return _result(action, content=json.dumps({"elements": []}))
        return _result(action, content="ok")

    monkeypatch.setattr("octop_browser.record.replay.browser_tool", fake_browser_tool)
    store = _store_with_steps(
        tmp_path,
        "rec_check",
        StepsDocument(
            recordingId="rec_check",
            steps=[
                SemanticStep(
                    id="step_001",
                    kind="set_checked",
                    target={
                        "role": "checkbox",
                        "name": "Subscribe",
                        "selectorCandidates": ["#subscribe"],
                    },
                    value="true",
                )
            ],
        ),
    )

    report = await ReplayRunner(store).run("rec_check", profile="demo")

    assert report["status"] == "passed"
    eval_calls = [kwargs for action, kwargs in calls if action == "eval_js"]
    assert eval_calls
    assert "set_checked" in eval_calls[0]["expression"]
    assert "#subscribe" in eval_calls[0]["expression"]


@pytest.mark.asyncio
async def test_replay_supports_richer_document_verification(monkeypatch, tmp_path):
    calls: list[tuple[str, dict]] = []

    async def fake_browser_tool(action: str, **kwargs):
        calls.append((action, kwargs))
        if action == "eval_js":
            return _result(action, content="true")
        return _result(action, content="ok")

    monkeypatch.setattr("octop_browser.record.replay.browser_tool", fake_browser_tool)
    store = _store_with_steps(
        tmp_path,
        "rec_verify_rich",
        StepsDocument(
            recordingId="rec_verify_rich",
            steps=[
                SemanticStep(id="step_001", kind="open", url="https://example.com/done")
            ],
            verification=[
                {"type": "title_contains", "value": "Done"},
                {
                    "type": "element_text_contains",
                    "selector": "#result",
                    "value": "Saved",
                },
                {"type": "input_value_equals", "selector": "#query", "value": "beta"},
            ],
        ),
    )

    report = await ReplayRunner(store).run("rec_verify_rich", profile="demo")

    assert report["status"] == "passed"
    assert [v["type"] for v in report["verification"]] == [
        "title_contains",
        "element_text_contains",
        "input_value_equals",
    ]
    assert len([c for c in calls if c[0] == "eval_js"]) == 3


@pytest.mark.asyncio
async def test_replay_forces_new_tab_for_recorded_new_tab_steps(monkeypatch, tmp_path):
    calls: list[tuple[str, dict]] = []

    async def fake_browser_tool(action: str, **kwargs):
        calls.append((action, kwargs))
        if action == "new_tab":
            return _result(
                action,
                content=f"runtime_{len([c for c in calls if c[0] == 'new_tab'])}",
            )
        return _result(action, content="ok")

    monkeypatch.setattr("octop_browser.record.replay.browser_tool", fake_browser_tool)
    store = _store_with_steps(
        tmp_path,
        "rec_force_new_tabs",
        StepsDocument(
            recordingId="rec_force_new_tabs",
            steps=[
                SemanticStep(
                    id="step_001",
                    kind="open",
                    url="https://example.com/a",
                    target={"targetId": "tab_a"},
                ),
                SemanticStep(
                    id="step_002",
                    kind="new_tab",
                    url="https://example.com/b",
                    target={"targetId": "tab_b"},
                ),
                SemanticStep(
                    id="step_003",
                    kind="new_tab",
                    url="https://example.com/c",
                    target={"targetId": "tab_c"},
                ),
            ],
        ),
    )

    report = await ReplayRunner(store).run("rec_force_new_tabs", profile="demo")

    assert report["status"] == "passed"
    assert [call for call in calls if call[0] == "new_tab"] == [
        (
            "new_tab",
            {"profile": "demo", "url": "https://example.com/b", "force_new": True},
        ),
        (
            "new_tab",
            {"profile": "demo", "url": "https://example.com/c", "force_new": True},
        ),
    ]


@pytest.mark.asyncio
async def test_replay_skips_known_transient_auth_and_risk_navigation_steps(
    monkeypatch, tmp_path
):
    calls: list[tuple[str, dict]] = []

    async def fake_browser_tool(action: str, **kwargs):
        calls.append((action, kwargs))
        if action == "new_tab":
            return _result(action, content="runtime_tab")
        return _result(action, content="ok")

    monkeypatch.setattr("octop_browser.record.replay.browser_tool", fake_browser_tool)
    store = _store_with_steps(
        tmp_path,
        "rec_old_transient_steps",
        StepsDocument(
            recordingId="rec_old_transient_steps",
            steps=[
                SemanticStep(
                    id="step_001", kind="open", url="https://www.bilibili.com/"
                ),
                SemanticStep(
                    id="step_002",
                    kind="new_tab",
                    url="https://weibo.com/",
                    target={"targetId": "tab_weibo"},
                ),
                SemanticStep(
                    id="step_003",
                    kind="navigate",
                    url=(
                        "https://weibo.com/newlogin?tabtype=weibo&gid=102803"
                        "&openLoginLayer=0&url=https%3A%2F%2Fweibo.com%2F"
                    ),
                    target={"targetId": "tab_weibo"},
                ),
                SemanticStep(
                    id="step_004",
                    kind="navigate",
                    url=(
                        "https://wappass.baidu.com/static/captcha/tuxing_v2.html"
                        "?backurl=https%3A%2F%2Fwww.baidu.com%2Fs%3Fwd%3Dweather"
                    ),
                    target={"targetId": "tab_baidu"},
                ),
            ],
        ),
    )

    report = await ReplayRunner(store).run("rec_old_transient_steps", profile="demo")

    assert report["status"] == "passed"
    assert [step["status"] for step in report["steps"]] == [
        "passed",
        "passed",
        "skipped",
        "skipped",
    ]
    assert [call for call in calls if call[0] == "navigate"] == [
        ("navigate", {"profile": "demo", "url": "https://www.bilibili.com/"}),
    ]
