"""Integration tests for browser record/replay against a deterministic page."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from octop_browser.profile import ProfileManager
from octop_browser.record.models import PrivacySettings
from octop_browser.record.recorder import RecordController
from octop_browser.record.replay import ReplayRunner
from octop_browser.record.settings import RecordReplaySettings
from octop_browser.record.store import RecordingStore
from octop_browser.session import BrowserSession
from octop_browser.settings import OctopSettings
from octop_browser.tool_interface import browser_tool

DEMO_HTML = """
<!doctype html>
<meta charset="utf-8">
<title>Record replay demo</title>
<form id="demo-form" method="get" action="done.html">
  <label for="query">Search query</label>
  <input id="query" name="query" placeholder="Search query" />
  <button id="submit" type="submit">Search</button>
</form>
<div id="result"></div>
"""


@pytest.mark.integration
async def test_record_replay_local_form_end_to_end(tmp_path: Path):
    page = tmp_path / "demo.html"
    page.write_text(DEMO_HTML, encoding="utf-8")
    (tmp_path / "done.html").write_text(
        "<title>Done</title><h1>Done</h1>", encoding="utf-8"
    )
    url = page.as_uri()

    settings = OctopSettings(
        profiles_dir=tmp_path / "profiles",
        screenshots_dir=tmp_path / "screenshots",
        cdp_port_start=19222,
        browser_mode="headless",
    )
    profile_manager = ProfileManager(base_dir=tmp_path / "profiles")
    profile_manager.get_or_create("record-e2e")
    store = RecordingStore(RecordReplaySettings(base_dir=tmp_path / "rr"))

    recorder_session = None
    try:
        sess = await BrowserSession.create(
            profile="record-e2e",
            headless=True,
            profile_manager=profile_manager,
            settings=settings,
        )
    except RuntimeError as exc:
        # CI runners sometimes ship a non-functional chromium-browser stub;
        # treat unusable Chrome the same as "not installed".
        if "Chrome" in str(exc) or "Chromium" in str(exc):
            pytest.skip(f"Chrome/Chromium unavailable for integration: {exc}")
        raise
    try:
        await sess.navigate(url)
        # Inject the same settings/profile manager the session was built with,
        # otherwise the controller resolves a port from the ambient environment
        # and records a different browser than the one driven below.
        controller = RecordController(
            store, settings=settings, profile_manager=profile_manager
        )
        recorder_session, data = await controller.start_in_process(
            profile="record-e2e",
            privacy=PrivacySettings(
                input_policy="none", url_query_policy="none", screenshot_policy="off"
            ),
        )
        assert data["ok"] is True

        dom = await sess.dom_tree(level="structured")
        assert dom.success is True
        assert isinstance(dom.content, str)
        import json

        elements = json.loads(dom.content)["elements"]
        input_ref = next(e["ref"] for e in elements if e.get("nameAttr") == "query")
        button_ref = next(e["ref"] for e in elements if e.get("id") == "submit")
        await sess.fill("alpha", ref=input_ref)
        await sess.click(ref=button_ref)
        await asyncio.sleep(0.5)

        stopped = await recorder_session.stop(
            generate_steps=True, skill_name="local-form-e2e"
        )
        assert stopped["events"] >= 3
        assert stopped["steps"] >= 3
    finally:
        if recorder_session is not None:
            await recorder_session.close()
        # kill=True: the profile dir lives under tmp_path, so leaving Chrome
        # running would strand a process holding this port for later runs.
        await sess.close(kill=True)

    replay_profile_manager = ProfileManager(
        base_dir=tmp_path / "profiles", settings=settings
    )
    replay_profile_manager.get_or_create("replay-e2e")
    replay_sess = await BrowserSession.create(
        profile="replay-e2e",
        headless=True,
        profile_manager=replay_profile_manager,
        settings=settings,
    )
    await replay_sess.close(kill=True)

    try:
        report = await ReplayRunner(store).run(
            data["recordingId"],
            profile="replay-e2e",
            inputs={"query": "beta"},
        )
    finally:
        # ReplayRunner drives the shared browser_tool registry, which owns its
        # own session; reap it so the run does not strand a Chrome process.
        await browser_tool("close_session", profile="replay-e2e", kill=True)

    assert report["status"] == "passed"
    assert report["stepsLoaded"] >= 3
    assert any(s["kind"] == "fill" and s.get("matchedBy") for s in report["steps"])
    assert any(
        v["type"] == "url_contains" and v["status"] == "passed"
        for v in report["verification"]
    )
