import assert from "node:assert/strict";
import { join } from "node:path";
import { test } from "node:test";

import {
  shouldInstallSystemTray,
  trayExecutableFallback,
  trayIconCandidates,
  trayIconImagePath,
  trayMenuLabels,
} from "./tray";

test("Windows and Linux get a tray icon; macOS uses the Dock", () => {
  assert.equal(shouldInstallSystemTray("win32"), true);
  assert.equal(shouldInstallSystemTray("linux"), true);
  assert.equal(shouldInstallSystemTray("darwin"), false);
});

test("dev Windows loads the bundled ico and not the Electron executable", () => {
  const resourcesDir = join("desktop", "resources");
  const execPath = join("node_modules", "electron", "dist", "electron.exe");
  assert.deepEqual(
    trayIconCandidates({ platform: "win32", isPackaged: false, resourcesDir, execPath }),
    [join(resourcesDir, "icon.ico")],
  );
});

test("Linux tray uses the png, in dev and in the package", () => {
  const resourcesDir = join("desktop", "resources");
  const execPath = join("node_modules", "electron", "dist", "electron");
  const png = join(resourcesDir, "icon.png");
  for (const isPackaged of [false, true]) {
    assert.deepEqual(
      trayIconCandidates({ platform: "linux", isPackaged, resourcesDir, execPath }),
      [png],
    );
  }
  assert.equal(trayIconImagePath([png], (path) => path === png), png);
});

test("packaged Windows falls back to the icon embedded in the executable", () => {
  const resourcesDir = join("install", "resources");
  const execPath = join("install", "Octop.exe");
  assert.deepEqual(
    trayIconCandidates({ platform: "win32", isPackaged: true, resourcesDir, execPath }),
    [join(resourcesDir, "icon.ico"), execPath],
  );
});

test("the tray image is the ico, never the executable", () => {
  const resourcesDir = join("install", "resources");
  const execPath = join("install", "Octop.exe");
  const candidates = trayIconCandidates({
    platform: "win32",
    isPackaged: true,
    resourcesDir,
    execPath,
  });
  const ico = join(resourcesDir, "icon.ico");
  assert.equal(
    trayIconImagePath(candidates, (path) => path === ico),
    ico,
  );
  assert.equal(
    trayIconImagePath(candidates, () => false),
    null,
  );
  assert.equal(trayExecutableFallback(candidates), execPath);
  assert.equal(trayExecutableFallback([ico]), null);
});

test("tray menu follows the OS locale", () => {
  assert.deepEqual(trayMenuLabels("zh-CN"), { show: "显示窗口", quit: "退出" });
  assert.deepEqual(trayMenuLabels("en-US"), { show: "Show window", quit: "Quit" });
});
