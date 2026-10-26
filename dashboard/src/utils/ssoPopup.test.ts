import { afterEach, describe, expect, it, vi } from "vitest";
import { isSsoPopup, notifySsoOpener, SSO_MESSAGE_TYPE } from "./ssoPopup";

/** Stub window.opener; omitting `location` simulates cross-origin access. */
function stubOpener(opener: Record<string, unknown> | null) {
  Object.defineProperty(window, "opener", {
    value: opener,
    configurable: true,
    writable: true,
  });
}

const sameOriginOpener = () => ({
  closed: false,
  location: { origin: window.location.origin },
  postMessage: vi.fn(),
});

const crossOriginOpener = () => ({
  closed: false,
  // Browsers throw a SecurityError when reading location.origin from a
  // cross-origin window; mirror that with a throwing getter.
  get location() {
    throw new DOMException("Permission denied", "SecurityError");
  },
  postMessage: vi.fn(),
});

describe("isSsoPopup", () => {
  afterEach(() => {
    stubOpener(null);
  });

  it("returns true for a same-origin opener", () => {
    stubOpener(sameOriginOpener());
    expect(isSsoPopup()).toBe(true);
  });

  it("returns false when there is no opener", () => {
    stubOpener(null);
    expect(isSsoPopup()).toBe(false);
  });

  it("returns false when the opener is closed", () => {
    stubOpener({ ...sameOriginOpener(), closed: true });
    expect(isSsoPopup()).toBe(false);
  });

  it("returns false for a cross-origin opener (portal tab)", () => {
    stubOpener(crossOriginOpener());
    expect(isSsoPopup()).toBe(false);
  });
});

describe("notifySsoOpener", () => {
  afterEach(() => {
    stubOpener(null);
    vi.restoreAllMocks();
  });

  it("posts to a same-origin opener and closes the tab", () => {
    const opener = sameOriginOpener();
    stubOpener(opener);
    const closeSpy = vi.spyOn(window, "close").mockImplementation(() => {});

    expect(notifySsoOpener({ ok: true, access_token: "tok" })).toBe(true);
    expect(opener.postMessage).toHaveBeenCalledWith(
      { type: SSO_MESSAGE_TYPE, ok: true, access_token: "tok" },
      window.location.origin,
    );
    expect(closeSpy).toHaveBeenCalled();
  });

  it("keeps the tab (no post, no close) for a cross-origin opener", () => {
    const opener = crossOriginOpener();
    stubOpener(opener);
    const closeSpy = vi.spyOn(window, "close").mockImplementation(() => {});

    expect(notifySsoOpener({ ok: true, access_token: "tok" })).toBe(false);
    expect(opener.postMessage).not.toHaveBeenCalled();
    expect(closeSpy).not.toHaveBeenCalled();
  });
});
