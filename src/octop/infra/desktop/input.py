"""Input injection, coordinates, and shortcut actions for remote desktop."""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
from collections.abc import Callable
from typing import Any

from octop.infra.desktop.capture import display_env, is_linux_virtual_display

logger = logging.getLogger(__name__)

_XDOTOOL_TIMEOUT_S = 3.0
_XDOTOOL_BUTTON = {"left": "1", "right": "3", "middle": "2"}
_XDOTOOL_KEYS: dict[str, str] = {
    "Enter": "Return",
    "Backspace": "BackSpace",
    "Tab": "Tab",
    "Escape": "Escape",
    "Delete": "Delete",
    "ArrowUp": "Up",
    "ArrowDown": "Down",
    "ArrowLeft": "Left",
    "ArrowRight": "Right",
    "Home": "Home",
    "End": "End",
    "PageUp": "Page_Up",
    "PageDown": "Page_Down",
    "Control": "ctrl",
    "Shift": "shift",
    "Alt": "alt",
    "Meta": "super",
    " ": "space",
}
for _i in range(1, 13):
    _XDOTOOL_KEYS[f"F{_i}"] = f"F{_i}"


def _ensure_pynput() -> tuple[Any, Any, dict[str, Any], dict[str, Any]]:
    from pynput.keyboard import Controller as KeyboardController
    from pynput.keyboard import Key
    from pynput.mouse import Button
    from pynput.mouse import Controller as MouseController

    button_map = {
        "left": Button.left,
        "right": Button.right,
        "middle": Button.middle,
    }
    special_keys = {
        "Enter": Key.enter,
        "Backspace": Key.backspace,
        "Tab": Key.tab,
        "Escape": Key.esc,
        "Delete": Key.delete,
        "ArrowUp": Key.up,
        "ArrowDown": Key.down,
        "ArrowLeft": Key.left,
        "ArrowRight": Key.right,
        "Home": Key.home,
        "End": Key.end,
        "PageUp": Key.page_up,
        "PageDown": Key.page_down,
        "Control": Key.ctrl,
        "Shift": Key.shift,
        "Alt": Key.alt,
        "Meta": Key.cmd,
        " ": Key.space,
    }
    for i in range(1, 13):
        attr = f"f{i}"
        if hasattr(Key, attr):
            special_keys[f"F{i}"] = getattr(Key, attr)
    return MouseController, KeyboardController, button_map, special_keys


def _xdotool_env(display: str | None) -> dict[str, str]:
    env = os.environ.copy()
    if display:
        env["DISPLAY"] = display
    return env


def _run_xdotool(display: str | None, args: list[str]) -> bool:
    if not shutil.which("xdotool"):
        return False
    try:
        proc = subprocess.run(
            ["xdotool", *args],
            env=_xdotool_env(display),
            capture_output=True,
            timeout=_XDOTOOL_TIMEOUT_S,
            check=False,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
            if detail:
                logger.debug("xdotool failed: %s", detail)
            return False
        return True
    except (OSError, subprocess.TimeoutExpired):
        logger.warning("xdotool timed out (display=%s)", display)
        return False


def _xdotool_key_name(key: str) -> str:
    if key in _XDOTOOL_KEYS:
        return _XDOTOOL_KEYS[key]
    if len(key) == 1:
        return key
    return key


class InputInjector:
    def __init__(self, *, display: str | None = None) -> None:
        self._display = display
        self._mouse: Any | None = None
        self._keyboard: Any | None = None
        self._button_map: dict[str, Any] | None = None
        self._special_keys: dict[str, Any] | None = None

    def _use_xdotool(self) -> bool:
        return is_linux_virtual_display(self._display) and shutil.which("xdotool") is not None

    def _controllers(self) -> tuple[Any, Any]:
        if self._mouse is None or self._keyboard is None:
            with display_env(self._display):
                mouse_cls, keyboard_cls, button_map, special_keys = _ensure_pynput()
                self._mouse = mouse_cls()
                self._keyboard = keyboard_cls()
                self._button_map = button_map
                self._special_keys = special_keys
        assert self._mouse is not None and self._keyboard is not None
        return self._mouse, self._keyboard

    def _with_display(self, fn: Any) -> None:
        with display_env(self._display):
            fn()

    def _button(self, name: str) -> Any:
        self._controllers()
        assert self._button_map is not None
        return self._button_map.get(name, self._button_map["left"])

    def click(self, x: int, y: int, *, button: str = "left", clicks: int = 1) -> None:
        if self._use_xdotool():
            btn = _XDOTOOL_BUTTON.get(button, "1")
            args = ["mousemove", str(x), str(y), "click"]
            if clicks > 1:
                args.extend(["--repeat", str(clicks)])
            args.append(btn)
            _run_xdotool(self._display, args)
            return

        def _do() -> None:
            mouse, _ = self._controllers()
            mouse.position = (x, y)
            mouse.click(self._button(button), clicks)

        self._with_display(_do)

    def mouse_down(self, x: int, y: int, *, button: str = "left") -> None:
        if self._use_xdotool():
            btn = _XDOTOOL_BUTTON.get(button, "1")
            _run_xdotool(
                self._display,
                ["mousemove", str(x), str(y), "mousedown", btn],
            )
            return

        def _do() -> None:
            mouse, _ = self._controllers()
            mouse.position = (x, y)
            mouse.press(self._button(button))

        self._with_display(_do)

    def mouse_up(self, x: int, y: int, *, button: str = "left") -> None:
        if self._use_xdotool():
            btn = _XDOTOOL_BUTTON.get(button, "1")
            _run_xdotool(
                self._display,
                ["mousemove", str(x), str(y), "mouseup", btn],
            )
            return

        def _do() -> None:
            mouse, _ = self._controllers()
            mouse.position = (x, y)
            mouse.release(self._button(button))

        self._with_display(_do)

    def mouse_move(self, x: int, y: int) -> None:
        if self._use_xdotool():
            _run_xdotool(self._display, ["mousemove", str(x), str(y)])
            return

        def _do() -> None:
            mouse, _ = self._controllers()
            mouse.position = (x, y)

        self._with_display(_do)

    def scroll(self, x: int, y: int, *, delta_x: float, delta_y: float) -> None:
        if self._use_xdotool():
            _run_xdotool(self._display, ["mousemove", str(x), str(y)])
            if abs(delta_y) >= 0.5:
                btn = "5" if delta_y > 0 else "4"
                steps = max(1, int(abs(delta_y) / 40))
                for _ in range(steps):
                    _run_xdotool(self._display, ["click", btn])
            if abs(delta_x) >= 0.5:
                btn = "6" if delta_x > 0 else "7"
                steps = max(1, int(abs(delta_x) / 40))
                for _ in range(steps):
                    _run_xdotool(self._display, ["click", btn])
            return

        def _do() -> None:
            mouse, _ = self._controllers()
            mouse.position = (x, y)
            if abs(delta_y) >= 0.5:
                mouse.scroll(0, int(-delta_y / 40) or (-1 if delta_y > 0 else 1))
            if abs(delta_x) >= 0.5:
                mouse.scroll(int(-delta_x / 40) or (-1 if delta_x > 0 else 1), 0)

        self._with_display(_do)

    def type_text(self, text: str) -> None:
        if self._use_xdotool():
            _run_xdotool(self._display, ["type", "--delay", "0", "--", text])
            return

        def _do() -> None:
            _, keyboard = self._controllers()
            keyboard.type(text)

        self._with_display(_do)

    def key_down(self, key: str) -> None:
        if self._use_xdotool():
            _run_xdotool(self._display, ["keydown", _xdotool_key_name(key)])
            return

        def _do() -> None:
            _, keyboard = self._controllers()
            assert self._special_keys is not None
            resolved = self._special_keys.get(key)
            if resolved is not None:
                keyboard.press(resolved)
            elif len(key) == 1:
                keyboard.press(key)

        self._with_display(_do)

    def key_up(self, key: str) -> None:
        if self._use_xdotool():
            _run_xdotool(self._display, ["keyup", _xdotool_key_name(key)])
            return

        def _do() -> None:
            _, keyboard = self._controllers()
            assert self._special_keys is not None
            resolved = self._special_keys.get(key)
            if resolved is not None:
                keyboard.release(resolved)
            elif len(key) == 1:
                keyboard.release(key)

        self._with_display(_do)


def canvas_to_screen(
    x: float,
    y: float,
    *,
    canvas_width: int,
    canvas_height: int,
    screen_width: int,
    screen_height: int,
) -> tuple[int, int]:
    if canvas_width <= 0 or canvas_height <= 0:
        return int(x), int(y)
    sx = int(round(x * screen_width / canvas_width))
    sy = int(round(y * screen_height / canvas_height))
    sx = max(0, min(sx, max(screen_width - 1, 0)))
    sy = max(0, min(sy, max(screen_height - 1, 0)))
    return sx, sy


ActionRunner = Callable[[InputInjector], bool]
VoidRunner = Callable[[InputInjector], None]


def _action_display_env(display: str | None) -> dict[str, str]:
    env = os.environ.copy()
    if display:
        env["DISPLAY"] = display
    return env


def _spawn(command: list[str], *, display: str | None) -> bool:
    if not shutil.which(command[0]):
        return False
    try:
        subprocess.Popen(
            command,
            env=_action_display_env(display),
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except OSError:
        logger.warning("failed to spawn %s", command[0])
        return False


def _xdotool_key(combo: str, *, display: str | None) -> bool:
    if not shutil.which("xdotool"):
        return False
    try:
        proc = subprocess.run(
            ["xdotool", "key", combo],
            env=_action_display_env(display),
            capture_output=True,
            timeout=3,
            check=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _inject_chord(injector: InputInjector, keys: list[str]) -> None:
    for key in keys:
        injector.key_down(key)
    for key in reversed(keys):
        injector.key_up(key)


def _tap_key(injector: InputInjector, key: str) -> None:
    injector.key_down(key)
    injector.key_up(key)


def _linux_runners(display: str | None) -> dict[str, ActionRunner]:
    def key_combo(combo: str, fallback: list[str]) -> ActionRunner:
        def _run(injector: InputInjector) -> bool:
            if _xdotool_key(combo, display=display):
                return True
            try:
                _inject_chord(injector, fallback)
                return True
            except Exception:
                logger.exception("desktop key combo failed: %s", combo)
                return False

        return _run

    def spawn_first(commands: list[list[str]]) -> ActionRunner:
        def _run(_injector: InputInjector) -> bool:
            return any(_spawn(cmd, display=display) for cmd in commands)

        return _run

    return {
        "show_desktop": key_combo("ctrl+alt+d", ["Control", "Alt", "d"]),
        "open_menu": key_combo("alt+F1", ["Alt", "F1"]),
        "close_window": key_combo("alt+F4", ["Alt", "F4"]),
        "open_terminal": spawn_first([["xfce4-terminal"], ["x-terminal-emulator"], ["xterm"]]),
        "open_files": spawn_first([["thunar"], ["nautilus"], ["pcmanfm"]]),
    }


def _native_action(run: VoidRunner) -> ActionRunner:
    def _run(injector: InputInjector) -> bool:
        try:
            run(injector)
            return True
        except Exception:
            logger.exception("desktop native action failed")
            return False

    return _run


def _native_runners() -> dict[str, ActionRunner]:
    return {
        "show_desktop": _native_action(lambda inj: _inject_chord(inj, ["Meta", "d"])),
        "open_menu": _native_action(lambda inj: _tap_key(inj, "Meta")),
        "open_terminal": _native_action(lambda inj: _inject_chord(inj, ["Control", "Alt", "t"])),
        "open_files": _native_action(lambda inj: _inject_chord(inj, ["Meta", "e"])),
        "close_window": _native_action(lambda inj: _inject_chord(inj, ["Alt", "F4"])),
    }


def run_desktop_action(
    action: str,
    *,
    display: str | None,
    injector: InputInjector,
) -> bool:
    system = platform.system().lower()
    runners = _linux_runners(display) if system == "linux" else _native_runners()
    runner = runners.get(action)
    if runner is None:
        return False
    try:
        return runner(injector)
    except Exception:
        logger.exception("desktop action failed: %s", action)
        return False
