"""Built-in tool: ``desktop_screenshot``.

Cross-platform desktop / window capture. Returns a structured block
ready to be embedded in a multimodal message — same shape as
``send_file_to_user`` so downstream code can treat them uniformly.

Prefer :func:`build_desktop_screenshot_tool` so files land under the
agent workspace (``outbound/screenshots/`` by default), matching browser
screenshots.

Backends
--------
- Linux virtual seats (TigerVNC / Xvfb ``:1``, ``:99``, …): prefer
  ImageMagick ``import``, then ``mss`` with the ``xlib`` backend
  (default / ``xgetimage`` often fail on VNC visuals).
- Other platforms: ``mss`` full-screen capture, trying multiple backends.
- macOS only, when ``capture_window=True``: the system ``screencapture``
  binary, which lets the user click a specific window to capture.

``mss`` is an optional dependency: install it explicitly or via the
``[desktop]`` extras (``pip install octop-harness[desktop]``).
ImageMagick ``import`` is an optional fallback used on virtual displays.
"""

from __future__ import annotations

import contextlib
import os
import platform
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from langchain_core.tools import tool

from octop_harness.builtin.tools.send_file import (
    build_send_file_to_user_tool,
    send_file_to_user,
)

if TYPE_CHECKING:
    from octop_harness.backends.workspace import BackendWorkspace

_MSS_BACKENDS = ("xlib", "xgetimage", "default")

# Same layout as browser screenshots / IM outbound media.
DEFAULT_SCREENSHOTS_DIR = "outbound/screenshots"


def _ensure_png_name(name: str) -> str:
    cleaned = name.strip().rstrip("/\\")
    if not cleaned.lower().endswith(".png"):
        cleaned = f"{cleaned}.png"
    return cleaned


def _resolve_screenshot_fragment(workspace: BackendWorkspace, path: str) -> str:
    """Map *path* to a workspace-relative PNG under ``outbound/screenshots/``.

    Dashboard media delivery only treats ``outbound/`` / ``inbound/`` as
    first-class workspace media; files elsewhere get copied and often fail
    preview. Always land screenshots in ``outbound/screenshots/``.
    """
    cleaned = (path or "").strip()
    if not cleaned:
        return f"{DEFAULT_SCREENSHOTS_DIR}/harness_screenshot_{int(time.time())}.png"

    expanded = Path(cleaned).expanduser()
    if cleaned.startswith("~") or expanded.is_absolute() or cleaned.startswith("/"):
        try:
            rel = expanded.resolve().relative_to(workspace.workspace_dir.resolve())
            fragment = rel.as_posix()
        except ValueError:
            fragment = expanded.name
    else:
        fragment = cleaned.replace("\\", "/")
        if fragment.startswith("./"):
            fragment = fragment[2:]

    fragment = _ensure_png_name(fragment)
    if fragment.startswith(("outbound/", "inbound/")):
        return fragment
    return f"{DEFAULT_SCREENSHOTS_DIR}/{Path(fragment).name}"


def _local_capture_path(workspace: BackendWorkspace, fragment: str) -> Path | None:
    """Return a host path under ``workspace_dir`` suitable for mss/import, if any."""
    storage = workspace.resolve_path(fragment)
    candidate = Path(storage)
    try:
        candidate.resolve().relative_to(workspace.workspace_dir.resolve())
    except ValueError:
        return None
    return candidate


def _prepare_parent(workspace: BackendWorkspace, fragment: str) -> None:
    parent = Path(fragment).parent.as_posix()
    if parent in {"", "."}:
        return
    workspace.mkdir(parent)


def _resolve_display() -> str | None:
    """Pick an X11 display for capture.

    Order: ``DISPLAY``; otherwise the first live socket under
    ``/tmp/.X11-unix`` (prefer a virtual seat ``:N`` with ``N != 0`` when
    several exist — typical for headless VNC / remote-desktop setups).
    """
    value = (os.environ.get("DISPLAY") or "").strip()
    if value:
        return value
    if platform.system() != "Linux":
        return None
    xdir = Path("/tmp/.X11-unix")
    if not xdir.is_dir():
        return None
    seats: list[tuple[int, str]] = []
    for sock in xdir.iterdir():
        name = sock.name
        if not name.startswith("X") or not name[1:].isdigit():
            continue
        if not sock.exists():
            continue
        num = int(name[1:])
        seats.append((num, f":{num}"))
    if not seats:
        return None
    seats.sort(key=lambda item: (0 if item[0] != 0 else 1, item[0]))
    return seats[0][1]


def _is_linux_virtual_display(display: str | None) -> bool:
    if platform.system() != "Linux" or not display:
        return False
    if not display.startswith(":"):
        return False
    head = display[1:].split(".", 1)[0]
    try:
        return int(head) != 0
    except ValueError:
        return False


def _capture_imagemagick(path: str, display: str) -> None:
    """Full-screen capture via ImageMagick ``import``."""
    import_bin = shutil.which("import")
    if not import_bin:
        raise RuntimeError("ImageMagick 'import' is not available")
    env = os.environ.copy()
    env["DISPLAY"] = display
    try:
        result = subprocess.run(
            [
                import_bin,
                "-silent",
                "-display",
                display,
                "-window",
                "root",
                path,
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"ImageMagick import timed out capturing display {display}",
        ) from exc
    if result.returncode != 0 or not Path(path).is_file():
        detail = (result.stderr or result.stdout or "").strip() or "unknown error"
        raise RuntimeError(f"ImageMagick import failed: {detail}")


def _capture_mss(path: str, display: str | None) -> None:
    """Full-screen capture via ``mss``, trying backends that work on VNC."""
    try:
        from mss import MSS
    except ImportError as exc:
        raise RuntimeError(
            "desktop_screenshot requires the 'mss' package. "
            "Install with: pip install 'octop-harness[desktop]'  "
            "(or: pip install mss).",
        ) from exc

    errors: list[str] = []
    for backend in _MSS_BACKENDS:
        sct = None
        try:
            kwargs: dict[str, Any] = {"backend": backend}
            if display:
                kwargs["display"] = display
            sct = MSS(**kwargs)
            # mon=0 = virtual monitor spanning all screens.
            sct.shot(mon=0, output=path)
            if Path(path).is_file():
                return
            errors.append(f"{backend}: no file written")
        except Exception as exc:  # try the next screenshot backend; pylint: disable=broad-except
            errors.append(f"{backend}: {exc}")
        finally:
            if sct is not None:
                with contextlib.suppress(Exception):
                    sct.close()

    detail = "; ".join(errors) if errors else "unknown error"
    raise RuntimeError(f"mss capture failed ({detail})")


def _capture_full_screen(path: str) -> None:
    """Full-screen capture. Raises ``RuntimeError`` on failure."""
    display = _resolve_display()
    errors: list[str] = []

    # TigerVNC seats often hang or fail under mss default backends —
    # prefer ImageMagick when available.
    if _is_linux_virtual_display(display) and shutil.which("import"):
        try:
            _capture_imagemagick(path, display or ":0")
            return
        except RuntimeError as exc:
            errors.append(str(exc))

    try:
        _capture_mss(path, display)
        return
    except RuntimeError as exc:
        errors.append(str(exc))

    if display and shutil.which("import"):
        try:
            _capture_imagemagick(path, display)
            return
        except RuntimeError as exc:
            errors.append(str(exc))

    hint = ""
    if platform.system() == "Linux" and not display:
        hint = (
            " No X11 display found (set DISPLAY, or start a graphical "
            "session / virtual desktop so /tmp/.X11-unix/X* exists)."
        )
    raise RuntimeError(
        "desktop_screenshot failed: " + " | ".join(errors) + hint,
    )


def _capture_window_macos(path: str) -> None:
    """Use macOS ``screencapture -w`` for click-to-capture window selection."""
    cmd = ["screencapture", "-x", "-w", path]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "screencapture timed out (likely the window picker was cancelled).",
        ) from exc

    if result.returncode != 0:
        stderr = (result.stderr or "").strip() or "Unknown error"
        raise RuntimeError(f"screencapture failed: {stderr}")
    if not Path(path).is_file():
        raise RuntimeError(
            "screencapture reported success but no file was created.",
        )


def _run_capture(path: str, *, capture_window: bool) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if platform.system() == "Darwin" and capture_window:
        _capture_window_macos(path)
    else:
        _capture_full_screen(path)


def build_desktop_screenshot_tool(workspace: BackendWorkspace) -> Any:
    """Return a ``desktop_screenshot`` tool bound to *workspace*.

    Screenshots are written under the agent workspace (default
    ``outbound/screenshots/``), with parent directories created as needed.
    """
    send_tool = build_send_file_to_user_tool(workspace)

    @tool
    def desktop_screenshot(
        path: str = "",
        capture_window: bool = False,
    ) -> dict[str, Any] | str:
        """Capture the desktop (or a single window on macOS) to a PNG file.

        Use this when the user asks to "take a screenshot", "show me what's
        on the screen", or you need to ground a UI-related answer in the
        current desktop state. The image is saved under
        ``outbound/screenshots/`` in the agent workspace and returned as a
        multimodal block (same shape as ``send_file_to_user``). **Do not**
        call ``send_file_to_user`` again on the result — the returned block
        is already the outbound media payload. Capture failures return
        ``"Error: …"`` instead of raising.

        Args:
            path: Optional filename or workspace-relative path. Always stored
                under ``outbound/screenshots/`` (basename only unless the path
                already starts with ``outbound/`` or ``inbound/``). Empty →
                timestamped file under ``outbound/screenshots/``.
            capture_window: macOS only. When True, the user is prompted to
                click a window to capture. Ignored on other platforms.
        """
        fragment = _resolve_screenshot_fragment(workspace, path)
        _prepare_parent(workspace, fragment)

        local = _local_capture_path(workspace, fragment)
        try:
            if local is not None:
                _run_capture(str(local), capture_window=capture_window)
                block = send_tool.invoke({"file_path": fragment})
            else:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
                    tmp = handle.name
                try:
                    _run_capture(tmp, capture_window=capture_window)
                    workspace.upload_bytes(fragment, Path(tmp).read_bytes())
                finally:
                    Path(tmp).unlink(missing_ok=True)
                block = send_tool.invoke({"file_path": fragment})
        except RuntimeError as exc:
            return f"Error: {exc}"

        if not isinstance(block, dict):  # pragma: no cover - defensive
            return f"Error: send_file_to_user returned non-dict: {type(block).__name__}"
        # Prefer workspace-relative outbound path so Octop media pipeline
        # recognizes the file without re-importing / copying.
        block["path"] = fragment
        return block

    return desktop_screenshot


@tool
def desktop_screenshot(
    path: str = "",
    capture_window: bool = False,
) -> dict[str, Any] | str:
    """Capture the desktop to a PNG (process temp dir; no agent workspace).

    Prefer :func:`build_desktop_screenshot_tool` on a :class:`HarnessAgent`
    so screenshots land under the agent workspace like browser captures.
    Capture failures return ``"Error: …"`` instead of raising.
    """
    cleaned = (path or "").strip()
    if not cleaned:
        target = os.path.join(
            tempfile.gettempdir(),
            f"harness_screenshot_{int(time.time())}.png",
        )
    else:
        candidate = Path(cleaned).expanduser()
        if not candidate.is_absolute():
            candidate = Path(tempfile.gettempdir()) / candidate
        if candidate.suffix.lower() != ".png":
            candidate = Path(str(candidate).rstrip("/\\") + ".png")
        target = str(candidate)

    try:
        _run_capture(target, capture_window=capture_window)
        block = send_file_to_user.invoke({"file_path": target})
    except RuntimeError as exc:
        return f"Error: {exc}"
    if not isinstance(block, dict):  # pragma: no cover - defensive
        return f"Error: send_file_to_user returned non-dict: {type(block).__name__}"
    block["path"] = str(Path(target).absolute())
    return block
