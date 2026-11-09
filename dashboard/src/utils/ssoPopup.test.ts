import { afterEach, describe, expect, it, vi } from "vitest";
import { isSsoPopup, notifySsoOpener, openSsoPopup } from "./ssoPopup";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("SSO popup detection", () => {
  it("requires the Octop popup name as well as an active opener", () => {
    vi.stubGlobal("opener", { closed: false });
    vi.stubGlobal("name", "portal-window");
    expect(isSsoPopup()).toBe(false);

    vi.stubGlobal("name", "octop-sso");
    expect(isSsoPopup()).toBe(true);

    vi.stubGlobal("opener", { closed: true });
    expect(isSsoPopup()).toBe(false);
  });

  it("does not notify or close an unrelated opener window", () => {
    const postMessage = vi.fn();
    vi.stubGlobal("name", "portal-window");
    vi.stubGlobal("opener", { closed: false, postMessage });

    expect(notifySsoOpener({ ok: false, error: "state" })).toBe(false);
    expect(postMessage).not.toHaveBeenCalled();
  });

  it("opens the popup with the name used for detection", () => {
    const popup = {} as Window;
    vi.spyOn(window, "open").mockReturnValue(popup);

    expect(openSsoPopup()).toBe(popup);
    expect(window.open).toHaveBeenCalledWith(
      "about:blank",
      "octop-sso",
      "popup=yes,width=520,height=720,noopener=no",
    );
  });
});
