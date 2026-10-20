"""octop-browser command-line entry point.

Subcommands fall into three groups:

- ``install-browser`` — bootstrap a Chromium binary via Playwright.
- Browser actions — every ``BrowserSession`` action exposed as a subcommand
  (``navigate``, ``dom-tree``, ``screenshot``, ``click``, ``type``,
  ``scroll``, ``hover``, ``eval-js``, ``go-back``, ``go-forward``,
  ``reload``, ``new-tab``, ``switch-tab``, ``close-tab``, ``list-tabs``,
  ``close-session``). Each call short-circuits to an attach if Chrome is
  already running on the profile's CDP port, so a sequence of CLI
  invocations shares one browser session.
- Output: human-readable text by default; ``--json`` returns the full
  ``ToolResult`` payload (success / content / metrics / metadata / error).

Sessions persist between calls because the launcher attaches to the
existing CDP port (see ``cdp.launcher.launch_or_attach``). Use
``octop-browser close-session --profile <name>`` to tear it down.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from octop_browser.install import chromium_executable, ensure_chromium
from octop_browser.mode import BrowserMode
from octop_browser.models import ToolResult
from octop_browser.record.daemon import ensure_daemon, send_request
from octop_browser.record.models import PrivacySettings
from octop_browser.record.recorder import RecordController
from octop_browser.record.replay import ReplayRunner
from octop_browser.record.store import RecordingStore
from octop_browser.tool_interface import browser_tool

# ---------------------------------------------------------------------------
# Subparser builders
# ---------------------------------------------------------------------------


def _package_version() -> str:
    """Return the installed package version for ``--version`` output."""
    try:
        return version("octop-browser")
    except PackageNotFoundError:
        return "unknown"


def _add_common_args(p: argparse.ArgumentParser) -> None:
    """Profile + output-format flags shared by every action subcommand."""
    p.add_argument(
        "--profile",
        default="default",
        help="Profile name (Chrome user-data-dir). Default: 'default'.",
    )
    p.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output the full ToolResult as JSON (success/content/metrics/metadata).",
    )


def _add_mode_args(p: argparse.ArgumentParser) -> None:
    """Launch-mode override; only honoured on the *first* call per profile."""
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--headed",
        dest="mode",
        action="store_const",
        const="headed",
        help="Force a headed browser (only effective on first call per profile).",
    )
    g.add_argument(
        "--headless",
        dest="mode",
        action="store_const",
        const="headless",
        help="Force a headless browser (only effective on first call per profile).",
    )
    g.add_argument(
        "--auto",
        dest="mode",
        action="store_const",
        const="auto",
        help="Auto-detect based on $DISPLAY (default).",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="octop-browser",
        description=(
            "octop-browser CLI — drive a CDP browser from the shell.\n"
            "Run '<command> --help' for command-specific options."
        ),
        epilog=(
            "Examples:\n"
            "  octop-browser navigate https://example.com --profile work\n"
            "  octop-browser dom-tree --level interactive --profile work\n"
            "  octop-browser record start --privacy mask-sensitive"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s " + _package_version(),
        help="Show the installed version and exit.",
    )
    sub = parser.add_subparsers(
        dest="command",
        required=True,
        metavar="<command>",
        title="commands",
    )

    # -- install-browser ----------------------------------------------------
    install = sub.add_parser(
        "install-browser",
        help="Install the managed Chromium binary used by the CDP launcher.",
        description=(
            "Install the managed Chromium binary that octop-browser can launch. "
            "Playwright may be bootstrapped as a one-time downloader, but it "
            "is not used to drive the browser. "
            "Idempotent: if a binary is already present, prints its path "
            "and exits 0 without re-downloading."
        ),
    )
    install.add_argument(
        "--quiet", action="store_true", help="Suppress installer subprocess output."
    )

    # -- navigate -----------------------------------------------------------
    navigate = sub.add_parser("navigate", help="Navigate to a URL.")
    navigate.add_argument("url", help="Destination URL.")
    _add_common_args(navigate)
    _add_mode_args(navigate)

    # -- open ---------------------------------------------------------------
    open_cmd = sub.add_parser(
        "open",
        help="Launch browser and open multiple URLs as tabs.",
        description=(
            "Start a browser session and open all given URLs as separate "
            "tabs. The first URL becomes the active tab. If the browser is "
            "already running for the profile, each URL is opened in a new "
            "tab."
        ),
    )
    open_cmd.add_argument(
        "urls",
        nargs="+",
        metavar="URL",
        help="URLs to open as separate tabs.",
    )
    _add_common_args(open_cmd)
    _add_mode_args(open_cmd)

    # -- dom-tree -----------------------------------------------------------
    dom = sub.add_parser(
        "dom-tree",
        help="Print the DOM tree (default: interactive).",
        description=(
            "Levels:\n"
            "  minimal     ~50 tokens   — title/url only\n"
            "  interactive ~200-500     — clickable/typeable refs (default)\n"
            "  full        ~1k-3k       — full readable page\n"
            "  structured  varies       — JSON for programmatic use"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    dom.add_argument(
        "--level",
        choices=["minimal", "interactive", "full", "structured"],
        default="interactive",
    )
    _add_common_args(dom)
    _add_mode_args(dom)

    # -- screenshot ---------------------------------------------------------
    shot = sub.add_parser(
        "screenshot", help="Capture a PNG; returns the saved file path."
    )
    shot.add_argument("--full-page", action="store_true", help="Capture entire page.")
    shot.add_argument(
        "--element-ref",
        help="Crop to a specific element ref (mutually exclusive with --full-page).",
    )
    shot.add_argument("--path", help="Pin output path; overwrites on each call.")
    _add_common_args(shot)
    _add_mode_args(shot)

    # -- click --------------------------------------------------------------
    click = sub.add_parser("click", help="Click an element.")
    click_target = click.add_mutually_exclusive_group(required=True)
    click_target.add_argument("--ref", help="Ref from dom-tree.")
    click_target.add_argument("--selector", help="CSS selector.")
    click_target.add_argument(
        "--xy", nargs=2, type=int, metavar=("X", "Y"), help="Absolute coordinates."
    )
    _add_common_args(click)
    _add_mode_args(click)

    # -- type ---------------------------------------------------------------
    typ = sub.add_parser("type", help="Type text into the page.")
    typ.add_argument("text", help="Text to type.")
    type_target = typ.add_mutually_exclusive_group()
    type_target.add_argument("--ref", help="Ref to click before typing.")
    type_target.add_argument("--selector", help="CSS selector to click before typing.")
    _add_common_args(typ)
    _add_mode_args(typ)

    # -- fill ---------------------------------------------------------------
    fill = sub.add_parser("fill", help="Replace text in a field.")
    fill.add_argument("text", help="Text to fill.")
    fill_target = fill.add_mutually_exclusive_group()
    fill_target.add_argument("--ref", help="Ref to click before filling.")
    fill_target.add_argument("--selector", help="CSS selector to click before filling.")
    _add_common_args(fill)
    _add_mode_args(fill)

    # -- press --------------------------------------------------------------
    press = sub.add_parser("press", help="Press a keyboard key.")
    press.add_argument("key", help="Key name, e.g. Enter, Tab, Escape.")
    _add_common_args(press)
    _add_mode_args(press)

    # -- wait ---------------------------------------------------------------
    wait = sub.add_parser("wait", help="Wait for URL/text/selector condition.")
    wait.add_argument("--url-contains")
    wait.add_argument("--text")
    wait.add_argument("--selector")
    wait.add_argument("--timeout-ms", type=int, default=10000)
    _add_common_args(wait)
    _add_mode_args(wait)

    # -- select -------------------------------------------------------------
    select = sub.add_parser("select", help="Set a <select> element value.")
    select.add_argument("value")
    target = select.add_mutually_exclusive_group(required=True)
    target.add_argument("--ref")
    target.add_argument("--selector")
    _add_common_args(select)
    _add_mode_args(select)

    # -- scroll -------------------------------------------------------------
    scroll = sub.add_parser("scroll", help="Scroll the page.")
    scroll.add_argument(
        "--direction", choices=["up", "down", "left", "right"], default="down"
    )
    scroll.add_argument("--amount", type=int, default=300)
    _add_common_args(scroll)
    _add_mode_args(scroll)

    # -- hover --------------------------------------------------------------
    hover = sub.add_parser("hover", help="Hover over an element ref.")
    hover.add_argument("ref")
    _add_common_args(hover)
    _add_mode_args(hover)

    # -- eval-js ------------------------------------------------------------
    eval_js = sub.add_parser("eval-js", help="Evaluate JavaScript in the page.")
    eval_js.add_argument("expression")
    _add_common_args(eval_js)
    _add_mode_args(eval_js)

    # -- history nav --------------------------------------------------------
    for name, help_text in (
        ("go-back", "Browser back."),
        ("go-forward", "Browser forward."),
        ("reload", "Reload current page."),
    ):
        sp = sub.add_parser(name, help=help_text)
        _add_common_args(sp)
        _add_mode_args(sp)

    # -- tabs ---------------------------------------------------------------
    new_tab = sub.add_parser("new-tab", help="Open a new tab (optionally to URL).")
    new_tab.add_argument("--url", default=None)
    _add_common_args(new_tab)
    _add_mode_args(new_tab)

    switch_tab = sub.add_parser("switch-tab", help="Activate a tab by id.")
    switch_tab.add_argument("tab_id")
    _add_common_args(switch_tab)
    _add_mode_args(switch_tab)

    close_tab = sub.add_parser("close-tab", help="Close a tab by id.")
    close_tab.add_argument("--tab-id", default=None)
    _add_common_args(close_tab)
    _add_mode_args(close_tab)

    list_tabs = sub.add_parser("list-tabs", help="List open tabs.")
    _add_common_args(list_tabs)
    _add_mode_args(list_tabs)

    # -- close-session ------------------------------------------------------
    close = sub.add_parser(
        "close-session",
        help=(
            "Close the CDP connection for a profile. Chrome stays alive unless "
            "--kill is passed."
        ),
    )
    close.add_argument(
        "--kill",
        action="store_true",
        help="Also terminate the Chrome process and free its CDP port.",
    )
    _add_common_args(close)

    # -- record -------------------------------------------------------------
    record = sub.add_parser("record", help="Record browser workflows.")
    record_sub = record.add_subparsers(dest="record_command", required=True)

    rec_doctor = record_sub.add_parser("doctor", help="Check CDP recording readiness.")
    rec_doctor.add_argument("--profile", default="default")
    rec_doctor.add_argument("--json", dest="as_json", action="store_true")

    rec_daemon_start = record_sub.add_parser(
        "daemon-start", help="Start the long-lived record daemon."
    )
    rec_daemon_start.add_argument("--json", dest="as_json", action="store_true")

    rec_daemon_stop = record_sub.add_parser(
        "daemon-stop", help="Stop the record daemon."
    )
    rec_daemon_stop.add_argument("--json", dest="as_json", action="store_true")

    rec_status = record_sub.add_parser("status", help="Show active recording status.")
    rec_status.add_argument("--json", dest="as_json", action="store_true")

    rec_stop = record_sub.add_parser("stop", help="Stop the active daemon recording.")
    rec_stop.add_argument("--recording-id")
    rec_stop.add_argument("--name")
    rec_stop.add_argument("--no-generate-steps", action="store_true")
    rec_stop.add_argument("--json", dest="as_json", action="store_true")

    rec_start = record_sub.add_parser(
        "start",
        help=(
            "Start recording via the record daemon "
            "(with --duration, run an in-process session instead)."
        ),
    )
    rec_start.add_argument("--profile", default="default")
    rec_start.add_argument("--name")
    rec_start.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="If >0, keep recording for N seconds then stop.",
    )
    rec_start.add_argument(
        "--privacy",
        choices=["none", "mask-sensitive", "mask-all"],
        default="mask-sensitive",
    )
    rec_start.add_argument("--json", dest="as_json", action="store_true")

    rec_list = record_sub.add_parser("list", help="List recordings.")
    rec_list.add_argument("--json", dest="as_json", action="store_true")

    rec_show = record_sub.add_parser(
        "show", help="Show recording artifact paths and status."
    )
    rec_show.add_argument("recording_id")
    rec_show.add_argument("--json", dest="as_json", action="store_true")

    rec_steps = record_sub.add_parser(
        "generate-steps", help="Generate steps.json from events.jsonl."
    )
    rec_steps.add_argument("recording_id")
    rec_steps.add_argument("--json", dest="as_json", action="store_true")

    rec_skill = record_sub.add_parser(
        "generate-skill", help="Generate draft.skill.md from steps.json."
    )
    rec_skill.add_argument("recording_id")
    rec_skill.add_argument("--name")
    rec_skill.add_argument("--json", dest="as_json", action="store_true")

    # -- replay -------------------------------------------------------------
    replay = sub.add_parser("replay", help="Replay recorded workflows.")
    replay_sub = replay.add_subparsers(dest="replay_command", required=True)
    replay_run = replay_sub.add_parser("run", help="Run a recorded workflow.")
    replay_run.add_argument("recording_id")
    replay_run.add_argument("--profile", default="default")
    replay_run.add_argument(
        "--input",
        action="append",
        default=[],
        help="Input as key=value; may be repeated.",
    )
    replay_run.add_argument("--json", dest="as_json", action="store_true")

    return parser


# ---------------------------------------------------------------------------
# Action dispatch
# ---------------------------------------------------------------------------


# CLI subcommand → browser_tool action name
_ACTION_ALIAS = {
    "dom-tree": "dom_tree",
    "eval-js": "eval_js",
    "go-back": "go_back",
    "go-forward": "go_forward",
    "new-tab": "new_tab",
    "switch-tab": "switch_tab",
    "close-tab": "close_tab",
    "list-tabs": "list_tabs",
    "close-session": "close_session",
}


def _action_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    """Translate parsed argparse Namespace into ``browser_tool`` kwargs."""
    cmd = args.command
    kwargs: dict[str, Any] = {}

    if cmd == "open":
        kwargs["urls"] = args.urls
    elif cmd == "navigate":
        kwargs["url"] = args.url
    elif cmd == "dom-tree":
        kwargs["level"] = args.level
    elif cmd == "screenshot":
        if args.full_page:
            kwargs["full_page"] = True
        if args.element_ref:
            kwargs["element_ref"] = args.element_ref
        if args.path:
            kwargs["path"] = args.path
    elif cmd == "click":
        if args.ref:
            kwargs["ref"] = args.ref
        elif args.selector:
            kwargs["selector"] = args.selector
        elif args.xy:
            kwargs["x"], kwargs["y"] = args.xy
    elif cmd == "type":
        kwargs["text"] = args.text
        if args.ref:
            kwargs["ref"] = args.ref
        if args.selector:
            kwargs["selector"] = args.selector
    elif cmd == "fill":
        kwargs["text"] = args.text
        if args.ref:
            kwargs["ref"] = args.ref
        if args.selector:
            kwargs["selector"] = args.selector
    elif cmd == "press":
        kwargs["key"] = args.key
    elif cmd == "wait":
        if args.url_contains:
            kwargs["url_contains"] = args.url_contains
        if args.text:
            kwargs["text"] = args.text
        if args.selector:
            kwargs["selector"] = args.selector
        kwargs["timeout_ms"] = args.timeout_ms
    elif cmd == "select":
        kwargs["value"] = args.value
        if args.ref:
            kwargs["ref"] = args.ref
        if args.selector:
            kwargs["selector"] = args.selector
    elif cmd == "scroll":
        kwargs["direction"] = args.direction
        kwargs["amount"] = args.amount
    elif cmd == "hover":
        kwargs["ref"] = args.ref
    elif cmd == "eval-js":
        kwargs["expression"] = args.expression
    elif cmd == "new-tab":
        if args.url is not None:
            kwargs["url"] = args.url
    elif cmd == "switch-tab":
        kwargs["tab_id"] = args.tab_id
    elif cmd == "close-tab":
        if args.tab_id:
            kwargs["tab_id"] = args.tab_id
    elif cmd == "close-session":
        if args.kill:
            kwargs["kill"] = True
    # go-back / go-forward / reload / list-tabs: no kwargs

    return kwargs


def _format_result(result: ToolResult, as_json: bool) -> str:
    """Render a ToolResult for human or scripted consumption."""
    if as_json:
        return json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
    if not result.success:
        return f"ERROR: {result.error or '(no message)'}"
    content = result.content
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


async def _run_action(args: argparse.Namespace) -> int:
    action = _ACTION_ALIAS.get(args.command, args.command)
    kwargs = _action_kwargs(args)
    mode: BrowserMode | None = getattr(args, "mode", None)
    # The "open" command uses urls= to launch multiple tabs; the action
    # is list_tabs so the result shows which tabs were opened.
    if args.command == "open":
        action = "list_tabs"
    try:
        result = await browser_tool(
            action=action, profile=args.profile, mode=mode, **kwargs
        )
    # browser_tool catches its own errors; this is a final safety net.
    except Exception as exc:  # pragma: no cover  # pylint: disable=broad-except
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    out = _format_result(result, as_json=args.as_json)
    stream = sys.stdout if result.success else sys.stderr
    print(out, file=stream)
    return 0 if result.success else 1


async def _run_record(args: argparse.Namespace) -> int:
    controller = RecordController()
    try:
        if args.record_command == "doctor":
            data = await controller.doctor(profile=args.profile)
        elif args.record_command == "daemon-start":
            data = await ensure_daemon()
        elif args.record_command == "daemon-stop":
            data = await send_request({"command": "shutdown"})
        elif args.record_command == "status":
            data = await send_request({"command": "status"})
        elif args.record_command == "stop":
            data = await send_request(
                {
                    "command": "stop",
                    "recording_id": args.recording_id,
                    "generate_steps": not args.no_generate_steps,
                    "name": args.name,
                }
            )
        elif args.record_command == "start":
            if args.duration and args.duration > 0:
                privacy = PrivacySettings(
                    input_policy=args.privacy,
                    url_query_policy="mask-sensitive",
                    screenshot_policy="off",
                )
                session, data = await controller.start_in_process(
                    profile=args.profile, privacy=privacy, name=args.name
                )
                await asyncio.sleep(args.duration)
                data.update(
                    await session.stop(generate_steps=True, skill_name=args.name)
                )
                await session.close()
            else:
                daemon = await ensure_daemon()
                if not daemon.get("ok"):
                    data = daemon
                else:
                    data = await send_request(
                        {
                            "command": "start",
                            "profile": args.profile,
                            "name": args.name,
                            "privacy": args.privacy,
                            "screenshots": "off",
                        }
                    )
        elif args.record_command == "list":
            data = {
                "recordings": [
                    m.model_dump(mode="json", by_alias=True)
                    for m in RecordingStore().list_recordings()
                ]
            }
        elif args.record_command == "show":
            data = {"ok": True, **RecordingStore().recording_summary(args.recording_id)}
        elif args.record_command == "generate-steps":
            data = controller.generate_steps(args.recording_id)
        elif args.record_command == "generate-skill":
            data = controller.generate_skill(args.recording_id, skill_name=args.name)
        else:
            data = {
                "ok": False,
                "error": f"Unknown record command {args.record_command}",
            }
    except Exception as exc:  # pylint: disable=broad-except
        data = {"ok": False, "error": str(exc)}
    print(json.dumps(data, ensure_ascii=False, indent=None if args.as_json else 2))
    return 0 if data.get("ok", True) else 1


async def _run_replay(args: argparse.Namespace) -> int:
    inputs: dict[str, str] = {}
    for item in args.input:
        if "=" in item:
            k, v = item.split("=", 1)
            inputs[k] = v
    try:
        data = await ReplayRunner().run(
            args.recording_id, profile=args.profile, inputs=inputs
        )
    except Exception as exc:  # pylint: disable=broad-except
        data = {"status": "failed", "error": str(exc)}
    print(json.dumps(data, ensure_ascii=False, indent=None if args.as_json else 2))
    return 0 if data.get("status") == "passed" else 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point used by ``[project.scripts] octop-browser``."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "install-browser":
        existing = chromium_executable()
        if existing:
            print(f"Chromium already installed: {existing}")
            return 0
        ok = ensure_chromium(quiet=args.quiet)
        return 0 if ok else 1
    if args.command == "record":
        return asyncio.run(_run_record(args))
    if args.command == "replay":
        return asyncio.run(_run_replay(args))

    return asyncio.run(_run_action(args))


if __name__ == "__main__":
    sys.exit(main())
