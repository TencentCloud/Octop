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

test("macOS 交通灯用系统常规尺寸，不拉高到页面顶栏", () => {
  assert.equal(chrome.TRAFFIC_LIGHT_BUTTON, 12);
  assert.equal(chrome.TRAFFIC_LIGHT_ROW_HEIGHT, 28);
  assert.ok(chrome.TRAFFIC_LIGHT_ROW_HEIGHT < chrome.CHROME_ROW_HEIGHT);
  assert.deepEqual(chrome.TRAFFIC_LIGHT_POSITION, { x: 12, y: 8 });
  onPlatform("darwin", () => {
    assert.deepEqual(chrome.windowChrome("light"), {
      titleBarStyle: "hidden",
      trafficLightPosition: { x: 12, y: 8 },
    });
  });
});

test("Windows 使用系统标题栏，菜单栏保持可见", () => {
  onPlatform("win32", () => {
    assert.deepEqual(chrome.windowChrome("light"), { autoHideMenuBar: false });
    assert.deepEqual(chrome.windowChrome("dark"), { autoHideMenuBar: false });
  });
});

test("主题切换不再把标题栏按钮画到页面上", () => {
  onPlatform("win32", () => {
    const win = {
      isDestroyed: () => false,
      setTitleBarOverlay: () => {
        throw new Error("titleBarOverlay should not be used");
      },
    } as unknown as BrowserWindow;
    chrome.applyWindowChromeTheme(win, { mode: "dark", scheme: "dark" });
    chrome.applyWindowChromeTheme(win, { mode: "light", scheme: "light" });
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
