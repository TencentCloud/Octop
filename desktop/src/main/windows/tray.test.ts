import assert from "node:assert/strict";
import { join } from "node:path";
import { test } from "node:test";

import { shouldInstallSystemTray, trayIconCandidates, trayMenuLabels } from "./tray";

test("only Windows gets a notification-area icon", () => {
  assert.equal(shouldInstallSystemTray("win32"), true);
  assert.equal(shouldInstallSystemTray("darwin"), false);
  assert.equal(shouldInstallSystemTray("linux"), false);
});

test("dev Windows loads the bundled ico and not the Electron executable", () => {
  const resourcesDir = join("desktop", "resources");
  const execPath = join("node_modules", "electron", "dist", "electron.exe");
  assert.deepEqual(
    trayIconCandidates({ platform: "win32", isPackaged: false, resourcesDir, execPath }),
    [join(resourcesDir, "icon.ico")],
  );
});

test("packaged Windows falls back to the icon embedded in the executable", () => {
  const resourcesDir = join("install", "resources");
  const execPath = join("install", "Octop.exe");
  assert.deepEqual(
    trayIconCandidates({ platform: "win32", isPackaged: true, resourcesDir, execPath }),
    [join(resourcesDir, "icon.ico"), execPath],
  );
});

test("tray menu follows the OS locale", () => {
  assert.deepEqual(trayMenuLabels("zh-CN"), { show: "显示窗口", quit: "退出" });
  assert.deepEqual(trayMenuLabels("en-US"), { show: "Show window", quit: "Quit" });
});
