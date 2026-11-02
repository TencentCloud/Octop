import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { test } from "node:test";
import type { BrowserWindow } from "electron";

// Node 测试不启动 Electron，只替换原生主题依赖，执行真实的窗口配置逻辑。
const hooks = registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier === "electron") {
      return {
        url: "data:text/javascript,export const nativeTheme = { shouldUseDarkColors: false, themeSource: 'system' };",
        shortCircuit: true,
      };
    }
    return nextResolve(specifier, context);
  },
});

const chrome = await import("./chrome").finally(() => hooks.deregister());

function onPlatform(platform: NodeJS.Platform, run: () => void): void {
  const original = Object.getOwnPropertyDescriptor(process, "platform");
  assert.ok(original);
  try {
    Object.defineProperty(process, "platform", { value: platform });
    run();
  } finally {
    Object.defineProperty(process, "platform", original);
  }
}

test("macOS 交通灯距左缘和上缘的距离相同", () => {
  assert.equal(chrome.CHROME_ROW_HEIGHT, 58);
  assert.deepEqual(chrome.TRAFFIC_LIGHT_POSITION, { x: 23, y: 23 });
  onPlatform("darwin", () => {
    assert.deepEqual(chrome.windowChrome("light"), {
      titleBarStyle: "hidden",
      trafficLightPosition: { x: 23, y: 23 },
    });
  });
});

test("Windows 标题栏覆盖整个 58px 顶栏且随主题变色", () => {
  onPlatform("win32", () => {
    for (const mode of ["light", "dark"] as const) {
      const overlay = chrome.titlebarOverlay(mode);
      assert.equal(overlay.height, 58);
      assert.equal(overlay.color, "#00000000");
      assert.equal(overlay.symbolColor, mode === "dark" ? "#e7e7ed" : "#1f2329");
      assert.deepEqual(chrome.windowChrome(mode), {
        frame: false,
        titleBarStyle: "hidden",
        titleBarOverlay: overlay,
      });
    }
  });
});

test("Windows 切换主题后仍保留 58px 原生标题栏", () => {
  onPlatform("win32", () => {
    const overlays: unknown[] = [];
    const win = {
      isDestroyed: () => false,
      setTitleBarOverlay: (overlay: unknown) => overlays.push(overlay),
    } as unknown as BrowserWindow;
    chrome.applyWindowChromeTheme(win, { mode: "dark" });
    chrome.applyWindowChromeTheme(win, { mode: "light" });
    assert.deepEqual(overlays, [
      { color: "#00000000", symbolColor: "#e7e7ed", height: 58 },
      { color: "#00000000", symbolColor: "#1f2329", height: 58 },
    ]);
  });
});

test("Linux 仍使用系统窗口边框", () => {
  onPlatform("linux", () => assert.deepEqual(chrome.windowChrome("light"), {}));
});

test("窗口底色与仪表盘启动地址跟设备主题走", () => {
  assert.equal(chrome.windowBackground("light"), "#f5f6f8");
  assert.equal(chrome.windowBackground("dark"), "#0e0e0e");
  assert.equal(chrome.dashboardEntryUrl("system"), "octop://app/?octopTheme=system");
  assert.equal(chrome.dashboardEntryUrl("dark"), "octop://app/?octopTheme=dark");
  assert.equal(
    chrome.dashboardEntryUrl("system", "http://127.0.0.1:5173"),
    "http://127.0.0.1:5173/?octopTheme=system",
  );
  assert.equal(chrome.isAppNavigation("octop://app/chat", "octop://app"), true);
  assert.equal(chrome.isAppNavigation("octop://apple", "octop://app"), false);
  assert.equal(
    chrome.isAppNavigation("http://127.0.0.1:5173/?octopTheme=system", "http://127.0.0.1:5173"),
    true,
  );
  assert.equal(chrome.isAppNavigation("http://127.0.0.1:51730/", "http://127.0.0.1:5173"), false);
  assert.equal(chrome.isAppNavigation("https://example.com", "http://127.0.0.1:5173"), false);
});
