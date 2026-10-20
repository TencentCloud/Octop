# pylint: disable=invalid-name
"""Demo: ``HarnessAgent.init_workspace()`` plus the media-aware built-in tools.

Walks through:

    1. ``HarnessAgent.init_workspace`` -- bootstrap a fresh workspace
       with the packaged markdown templates and built-in skills.
       Idempotent: a second call leaves user edits alone.
    2. ``current_time`` -- improved built-in tool with bilingual weekday.
    3. ``send_file_to_user`` -- wrap a local file as a multimodal content
       block for delivery to the user via a chat channel adapter.
    4. ``desktop_screenshot`` -- capture the screen (gracefully skipped
       when ``mss`` is not installed or running headless).

Run with::

    uv run python examples/06_init_and_md_files.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from octop_harness import HarnessAgent, HarnessAgentConfig, ModelConfig, ProviderConfig
from octop_harness.backends.utils import DEFENSIVE_OP_ERRORS
from octop_harness.builtin.tools import current_time, desktop_screenshot, send_file_to_user


def _heading(label: str) -> None:
    bar = "─" * 60
    print(f"\n{bar}\n {label}\n{bar}")


def _build_offline_agent(root: Path) -> HarnessAgent:
    """Construct a HarnessAgent suitable for filesystem operations only.

    No real LLM call is made in this example, so the API key/base_url
    are placeholders. The filesystem backend is rooted at ``root`` so
    we can inspect what ``init_workspace`` writes.

    Direct HarnessAgent access for workspace/backend operations
    (AgentManager doesn't expose init_workspace or .backend).
    """
    config = HarnessAgentConfig(
        workspace_dir=root,
        name="init-demo",
        backend={
            "type": "filesystem",
            "root_dir": str(root),
            "virtual_mode": True,
        },
        providers=[
            ProviderConfig(
                id="p",
                base_url="https://api.example.com/v1",
                api_key="sk-fake",
                models=[ModelConfig(id="placeholder", input=["text"])],
            ),
        ],
        default_model="p/placeholder",
        session_log_enabled=False,
    )
    return HarnessAgent(config)


def scenario_init_workspace(root: Path) -> Path:
    _heading("Scenario 1: HarnessAgent.init_workspace() bootstraps a workspace")

    agent = _build_offline_agent(root)
    result = agent.init_workspace()
    workspace = root / "workspace"

    print(f"workspace_path  : {result.workspace_path}")
    print(f"on disk         : {workspace}")
    print(f"created         : {[p.rsplit('/', 1)[-1] for p in result.templates_created]}")
    print(f"skipped         : {[p.rsplit('/', 1)[-1] for p in result.templates_skipped]}")
    print(f"skills_synced   : {result.skills_synced}")

    # Show that user edits are preserved by a second init_workspace() call.
    user_edit = workspace / "AGENTS.md"
    user_edit.write_text("# my custom AGENTS\n\nDo not lose me.\n", encoding="utf-8")

    again = _build_offline_agent(root).init_workspace()
    print(
        f"\nsecond init_workspace() → created={len(again.templates_created)}  "
        f"skipped={len(again.templates_skipped)}  "
        f"skills_synced={again.skills_synced}",
    )
    print(f"AGENTS.md after re-init: {user_edit.read_text(encoding='utf-8').splitlines()[0]!r}")
    return workspace


def scenario_current_time() -> None:
    _heading("Scenario 2: current_time (bilingual weekday)")

    print("local      :", current_time.invoke({}))
    print("UTC        :", current_time.invoke({"tz": "UTC"}))
    print("Shanghai   :", current_time.invoke({"tz": "Asia/Shanghai"}))


def scenario_send_file_to_user(workspace: Path) -> None:
    _heading("Scenario 3: send_file_to_user (multimodal block)")

    workspace.mkdir(parents=True, exist_ok=True)
    # Drop a tiny PNG (only the magic bytes; not a real image) plus an mp3.
    png = workspace / "demo.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")
    mp3 = workspace / "voice.mp3"
    mp3.write_bytes(b"ID3\x04\x00")

    img_block = send_file_to_user.invoke({"file_path": str(png)})
    audio_block = send_file_to_user.invoke({"file_path": str(mp3)})

    print("image block:")
    for k, v in img_block.items():
        print(f"  {k}: {v}")
    print("audio block:")
    for k, v in audio_block.items():
        print(f"  {k}: {v}")


def scenario_desktop_screenshot() -> None:
    _heading("Scenario 4: desktop_screenshot (mss)")
    if os.environ.get("HARNESS_SKIP_SCREENSHOT"):
        print("(skipped — HARNESS_SKIP_SCREENSHOT set)")
        return
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        print("(skipped — no $DISPLAY / $WAYLAND_DISPLAY; running headless)")
        return
    try:
        import mss as _mss  # noqa: F401 — probe for the optional dep
    except ImportError:
        print(
            "(skipped — `mss` is not installed; install with `pip install 'octop-harness[desktop]'`)",
        )
        return

    target = Path(tempfile.gettempdir()) / "harness_demo_screenshot.png"
    try:
        block = desktop_screenshot.invoke({"path": str(target)})
    except RuntimeError as exc:
        print(f"(capture failed: {exc})")
        return
    print(f"saved to     : {block['path']}")
    print(f"file://      : {block['source']['url']}")
    print(f"media_type   : {block['source']['media_type']}")


def main() -> None:
    # Use a real per-run directory so users can inspect what was created.
    root = Path("./.init_demo_root").absolute()
    root.mkdir(exist_ok=True)
    print(f"demo root: {root}")

    workspace_holder: dict[str, Path] = {}

    def _scenario_init() -> None:
        workspace_holder["workspace"] = scenario_init_workspace(root)

    def _scenario_preview() -> None:
        # Falls back to a fresh tmp dir if scenario 1 itself failed.
        workspace = workspace_holder.get("workspace") or root / "workspace"
        scenario_send_file_to_user(workspace)

    scenarios = [
        ("01_init", _scenario_init),
        ("02_time", scenario_current_time),
        ("03_preview", _scenario_preview),
        ("04_screenshot", scenario_desktop_screenshot),
    ]
    failures = 0
    for name, fn in scenarios:
        try:
            fn()
        except DEFENSIVE_OP_ERRORS as exc:
            failures += 1
            print(f"[!] scenario {name} raised: {type(exc).__name__}: {exc}")

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
