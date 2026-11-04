import { afterEach, describe, expect, it, vi } from "vitest";

import {
  isAuthPopupBlocked,
  navigateAuthWindow,
  openExternalBrowserUrl,
  tryOpenAuthPopup,
} from "./openAuthWindow";

type DesktopWindow = Window & {
  _wails?: { invoke?: (message: string) => void };
};

const originalOpen = window.open;

afterEach(() => {
  window.open = originalOpen;
  delete (window as DesktopWindow)._wails;
});

describe("tryOpenAuthPopup", () => {
  it("skips the placeholder window in the desktop shell", () => {
    const open = vi.fn();
    window.open = open as typeof window.open;
    (window as DesktopWindow)._wails = { invoke: () => undefined };
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
    (window as DesktopWindow)._wails = { invoke: () => undefined };
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
