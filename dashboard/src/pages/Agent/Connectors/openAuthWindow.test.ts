import { afterEach, describe, expect, it, vi } from "vitest";

import {
  isAuthPopupBlocked,
  navigateAuthWindow,
  openExternalBrowserUrl,
  tryOpenAuthPopup,
} from "./openAuthWindow";

type BridgeHost = Window & { octopDesktop?: unknown };

const originalOpen = window.open;

function stubDesktopBridge(): void {
  Object.defineProperty(window, "octopDesktop", {
    configurable: true,
    value: { windowControls: vi.fn() },
  });
}

afterEach(() => {
  window.open = originalOpen;
  delete (window as BridgeHost).octopDesktop;
});

describe("tryOpenAuthPopup", () => {
  it("skips the placeholder window in the desktop shell", () => {
    const open = vi.fn();
    window.open = open as typeof window.open;
    stubDesktopBridge();
    expect(
      tryOpenAuthPopup("", "octop-oauth", "width=520,height=720"),
    ).toBeNull();
    expect(open).not.toHaveBeenCalled();
    expect(isAuthPopupBlocked(null)).toBe(false);
  });

  it("still reports a blocked popup in the browser", () => {
    window.open = vi.fn(() => null) as typeof window.open;
    expect(
      tryOpenAuthPopup("", "octop-oauth", "width=520,height=720"),
    ).toBeNull();
    expect(isAuthPopupBlocked(null)).toBe(true);
  });
});

describe("navigateAuthWindow", () => {
  it("opens the system-browser tab on desktop even if a dummy popup exists", () => {
    const open = vi.fn(() => null);
    window.open = open as typeof window.open;
    stubDesktopBridge();
    const popup = {
      closed: false,
      location: { replace: vi.fn() },
      focus: vi.fn(),
    } as unknown as Window;
    navigateAuthWindow(popup, "https://example.com/authorize");
    expect(popup.location.replace).not.toHaveBeenCalled();
    expect(open).toHaveBeenCalledWith(
      "https://example.com/authorize",
      "_blank",
      "noopener,noreferrer",
    );
  });

  it("reuses the web popup when it is still open", () => {
    const open = vi.fn();
    window.open = open as typeof window.open;
    const popup = {
      closed: false,
      location: { replace: vi.fn() },
      focus: vi.fn(),
    } as unknown as Window;
    navigateAuthWindow(popup, "https://example.com/authorize");
    expect(popup.location.replace).toHaveBeenCalledWith(
      "https://example.com/authorize",
    );
    expect(open).not.toHaveBeenCalled();
  });
});

describe("openExternalBrowserUrl", () => {
  it("opens _blank so the desktop hook can hand off to the OS browser", () => {
    const open = vi.fn();
    window.open = open as typeof window.open;
    openExternalBrowserUrl("https://example.com/key");
    expect(open).toHaveBeenCalledWith(
      "https://example.com/key",
      "_blank",
      "noopener,noreferrer",
    );
  });
});
