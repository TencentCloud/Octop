#!/usr/bin/env python3
"""Deterministic record/replay smoke test for octop-browser.

This script is intentionally local-only: it creates a tiny form page, records
fill+submit through a real Chrome instance, generates steps/skill, then replays
with a different input and verifies the final URL.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from octop_browser.profile import ProfileManager
from octop_browser.record.models import PrivacySettings
from octop_browser.record.recorder import RecordController
from octop_browser.record.replay import ReplayRunner
from octop_browser.record.settings import RecordReplaySettings
from octop_browser.record.store import RecordingStore
from octop_browser.session import BrowserSession
from octop_browser.settings import OctopSettings

DEMO_HTML = """<!doctype html>
<meta charset=\"utf-8\">
<title>Smoke Demo</title>
<form id=\"demo-form\" method=\"get\" action=\"done.html\">
  <label for=\"query\">Search query</label>
  <input id=\"query\" name=\"query\" placeholder=\"Search query\" />
  <select id=\"country\" name=\"country\" aria-label=\"Country\">
    <option value=\"US\">US</option>
    <option value=\"CN\">CN</option>
  </select>
  <label><input id=\"subscribe\" type=\"checkbox\" /> Subscribe</label>
  <button id=\"submit\" type=\"submit\">Search</button>
</form>
"""

DONE_HTML = """<!doctype html>
<meta charset=\"utf-8\">
<title>Done</title>
<h1 id=\"result\">Done</h1>
"""


def _print(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


async def run_smoke(
    base: Path, *, headless: bool, cdp_port_start: int
) -> dict[str, Any]:
    base.mkdir(parents=True, exist_ok=True)
    page = base / "demo.html"
    page.write_text(DEMO_HTML, encoding="utf-8")
    (base / "done.html").write_text(DONE_HTML, encoding="utf-8")

    settings = OctopSettings(
        profiles_dir=base / "profiles",
        screenshots_dir=base / "screenshots",
        cdp_port_start=cdp_port_start,
        browser_mode="headless" if headless else "headed",
    )
    profile_manager = ProfileManager(base_dir=base / "profiles")
    store = RecordingStore(RecordReplaySettings(base_dir=base / "rr"))
    controller = RecordController(store)

    recording_session = None
    sess = await BrowserSession.create(
        profile="smoke-record",
        headless=headless,
        profile_manager=profile_manager,
        settings=settings,
    )
    try:
        await sess.navigate(page.as_uri())
        recording_session, start_data = await controller.start_in_process(
            profile="smoke-record",
            privacy=PrivacySettings(
                input_policy="none", url_query_policy="none", screenshot_policy="off"
            ),
            name="record-replay-smoke",
        )
        await sess.fill("alpha", selector="#query")
        await sess.select("CN", selector="#country")
        await sess.click(selector="#subscribe")
        await sess.click(selector="#submit")
        await asyncio.sleep(0.4)
        stop_data = await recording_session.stop(
            generate_steps=True, skill_name="record-replay-smoke"
        )
    finally:
        if recording_session is not None:
            await recording_session.close()
        await sess.close()

    replay_profile_manager = ProfileManager(base_dir=base / "profiles")
    replay_sess = await BrowserSession.create(
        profile="smoke-replay",
        headless=headless,
        profile_manager=replay_profile_manager,
        settings=settings,
    )
    await replay_sess.close()

    recording_id = start_data["recordingId"]
    report = await ReplayRunner(store).run(
        recording_id, profile="smoke-replay", inputs={"query": "beta", "country": "CN"}
    )
    summary = store.recording_summary(recording_id)
    return {
        "ok": report.get("status") == "passed",
        "recordingId": recording_id,
        "baseDir": str(base),
        "events": stop_data.get("events"),
        "steps": stop_data.get("steps"),
        "stepsPath": stop_data.get("stepsPath"),
        "skillDraft": stop_data.get("skillDraft"),
        "replayStatus": report.get("status"),
        "reportPath": report.get("reportPath"),
        "verification": report.get("verification"),
        "summary": summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic octop-browser record/replay smoke test."
    )
    parser.add_argument("--base-dir", type=Path, default=None)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--cdp-port-start",
        type=int,
        default=int(os.environ.get("BROWSER_USE_CDP_PORT_START", "19550")),
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    if args.base_dir is None:
        with TemporaryDirectory(prefix="hbr-smoke-") as tmp:
            payload = asyncio.run(
                run_smoke(
                    Path(tmp),
                    headless=not args.headed,
                    cdp_port_start=args.cdp_port_start,
                )
            )
            _print(payload, args.as_json)
            return 0 if payload["ok"] else 1
    payload = asyncio.run(
        run_smoke(
            args.base_dir, headless=not args.headed, cdp_port_start=args.cdp_port_start
        )
    )
    _print(payload, args.as_json)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
