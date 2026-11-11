import assert from "node:assert/strict";
import { test } from "node:test";

import {
  isWindowOnScreen,
  presentWindows,
  shouldKeepWindowOnClose,
  type PresentableWindow,
} from "./present";

function fakeWindow(state: { destroyed?: boolean; minimized?: boolean }): PresentableWindow & {
  calls: string[];
} {
  const calls: string[] = [];
  return {
    calls,
    isDestroyed: () => state.destroyed === true,
    isMinimized: () => state.minimized === true,
    restore: () => calls.push("restore"),
    show: () => calls.push("show"),
    focus: () => calls.push("focus"),
  };
}

test("Dock click restores a minimized window before showing it", () => {
  const win = fakeWindow({ minimized: true });
  assert.equal(presentWindows([win]), 1);
  assert.deepEqual(win.calls, ["restore", "show", "focus"]);
});

test("Dock click shows a hidden window without un-maximizing it", () => {
  const win = fakeWindow({ minimized: false });
  assert.equal(presentWindows([win]), 1);
  assert.deepEqual(win.calls, ["show", "focus"]);
});

test("a destroyed window is skipped", () => {
  const gone = fakeWindow({ destroyed: true });
  const live = fakeWindow({});
  assert.equal(presentWindows([gone, live]), 1);
  assert.deepEqual(gone.calls, []);
  assert.deepEqual(live.calls, ["show", "focus"]);
});

test("no windows means the caller should open one", () => {
  assert.equal(presentWindows([]), 0);
});

test("macOS tray close hides the window until the next Dock click", () => {
  assert.equal(
    shouldKeepWindowOnClose({ platform: "darwin", closeBehavior: "tray", quitting: false }),
    true,
  );
});

test("Windows and Linux tray close hides the window when the tray icon can open it", () => {
  for (const platform of ["win32", "linux"]) {
    assert.equal(
      shouldKeepWindowOnClose({
        platform,
        closeBehavior: "tray",
        quitting: false,
        trayReady: true,
      }),
      true,
    );
    assert.equal(
      shouldKeepWindowOnClose({
        platform,
        closeBehavior: "tray",
        quitting: false,
        trayReady: false,
      }),
      false,
    );
  }
});

test("quit, and closing while the app is exiting, lets the window close", () => {
  assert.equal(
    shouldKeepWindowOnClose({ platform: "darwin", closeBehavior: "quit", quitting: false }),
    false,
  );
  assert.equal(
    shouldKeepWindowOnClose({ platform: "darwin", closeBehavior: "tray", quitting: true }),
    false,
  );
  assert.equal(
    shouldKeepWindowOnClose({ platform: "win32", closeBehavior: "tray", quitting: false }),
    false,
  );
  assert.equal(
    shouldKeepWindowOnClose({
      platform: "win32",
      closeBehavior: "quit",
      quitting: false,
      trayReady: true,
    }),
    false,
  );
  assert.equal(
    shouldKeepWindowOnClose({
      platform: "linux",
      closeBehavior: "quit",
      quitting: false,
      trayReady: true,
    }),
    false,
  );
});

test("a window on a disconnected display is not on screen", () => {
  const laptop = { x: 0, y: 0, width: 1440, height: 900 };
  assert.equal(isWindowOnScreen({ x: 100, y: 100, width: 1080, height: 720 }, [laptop]), true);
  assert.equal(isWindowOnScreen({ x: 2000, y: 100, width: 1080, height: 720 }, [laptop]), false);
  assert.equal(isWindowOnScreen({ x: 1400, y: 100, width: 1080, height: 720 }, [laptop]), false);
});
