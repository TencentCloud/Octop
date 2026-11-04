import { afterEach, describe, expect, it, vi } from "vitest";

import {
  isDesktopExternalURL,
  isDesktopExternalWindowTarget,
  tryInstallDesktopExternalLinks,
} from "./desktopExternalLinks";

type DesktopWindow = Window & {
  __OCTOP_EXTERNAL_LINKS_INSTALLED__?: boolean;
  _wails?: { invoke?: (message: string) => void };
};

const originalOpen = window.open;

afterEach(() => {
  window.open = originalOpen;
  const w = window as DesktopWindow;
  delete w.__OCTOP_EXTERNAL_LINKS_INSTALLED__;
  delete w._wails;
});

describe("isDesktopExternalURL", () => {
  it("accepts http(s) and mailto, rejects about:blank", () => {
    expect(isDesktopExternalURL("https://example.com/oauth")).toBe(true);
    expect(isDesktopExternalURL("http://127.0.0.1:8080/login")).toBe(true);
    expect(isDesktopExternalURL("mailto:user@example.com")).toBe(true);
    expect(isDesktopExternalURL("about:blank")).toBe(false);
  });
});

describe("isDesktopExternalWindowTarget", () => {
  it("treats named connector popups like _blank", () => {
    expect(isDesktopExternalWindowTarget()).toBe(true);
    expect(isDesktopExternalWindowTarget("_blank")).toBe(true);
    expect(isDesktopExternalWindowTarget("octop-connector-auth")).toBe(true);
    expect(isDesktopExternalWindowTarget("_self")).toBe(false);
    expect(isDesktopExternalWindowTarget("_parent")).toBe(false);
    expect(isDesktopExternalWindowTarget("_top")).toBe(false);
  });
});

describe("tryInstallDesktopExternalLinks", () => {
  it("opens named connector auth windows in the system browser", () => {
    const invoke = vi.fn();
    (window as DesktopWindow)._wails = { invoke };
    const uninstall = tryInstallDesktopExternalLinks();
    expect(uninstall).toBeDefined();

    const result = window.open(
      "https://example.com/authorize",
      "octop-connector-auth",
      "width=720,height=800",
    );

    expect(result).toBeNull();
    expect(invoke).toHaveBeenCalledWith(
      "wails:event:emit:desktop:open-url:" +
        encodeURIComponent("https://example.com/authorize"),
    );
    uninstall?.();
  });

  it("leaves empty placeholder popups and in-page targets alone", () => {
    const invoke = vi.fn();
    const fallback = vi.fn(() => null);
    (window as DesktopWindow)._wails = { invoke };
    window.open = fallback as typeof window.open;
    const uninstall = tryInstallDesktopExternalLinks();

    window.open("", "octop-oauth", "width=520,height=720");
    window.open("https://example.com/next", "_self");
    window.open("about:blank", "octop-connector-auth");

    expect(invoke).not.toHaveBeenCalled();
    expect(fallback).toHaveBeenCalledTimes(3);
    uninstall?.();
  });
});
