import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearChunkReloadFlag,
  isChunkLoadError,
  tryReloadOnStaleChunk,
} from "./reloadOnStaleChunk";

describe("isChunkLoadError", () => {
  it("matches Vite dynamic import failures", () => {
    expect(
      isChunkLoadError(
        new Error(
          "Failed to fetch dynamically imported module: http://x/assets/Foo.js",
        ),
      ),
    ).toBe(true);
  });

  it("matches ChunkLoadError name", () => {
    const err = new Error("Loading chunk 3 failed.");
    err.name = "ChunkLoadError";
    expect(isChunkLoadError(err)).toBe(true);
  });

  it("rejects unrelated errors", () => {
    expect(isChunkLoadError(new Error("Network error"))).toBe(false);
    expect(isChunkLoadError(null)).toBe(false);
  });
});

describe("tryReloadOnStaleChunk", () => {
  const reload = vi.fn();

  beforeEach(() => {
    sessionStorage.clear();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { reload },
    });
    reload.mockClear();
  });

  afterEach(() => {
    clearChunkReloadFlag();
  });

  it("reloads once on chunk error", () => {
    const err = new Error("Failed to fetch dynamically imported module: /a.js");
    expect(tryReloadOnStaleChunk(err)).toBe(true);
    expect(reload).toHaveBeenCalledOnce();
    expect(sessionStorage.getItem("octop:chunk-reload")).toBe("1");
  });

  it("does not loop on a second consecutive chunk error", () => {
    const err = new Error("Failed to fetch dynamically imported module: /a.js");
    expect(tryReloadOnStaleChunk(err)).toBe(true);
    reload.mockClear();
    expect(tryReloadOnStaleChunk(err)).toBe(false);
    expect(reload).not.toHaveBeenCalled();
    expect(sessionStorage.getItem("octop:chunk-reload")).toBeNull();
  });

  it("ignores non-chunk errors", () => {
    expect(tryReloadOnStaleChunk(new Error("boom"))).toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });
});

describe("navigation-aborted chunk errors", () => {
  const reload = vi.fn();
  let mod: typeof import("./reloadOnStaleChunk");

  beforeEach(async () => {
    vi.resetModules();
    sessionStorage.clear();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { reload },
    });
    reload.mockClear();
    mod = await import("./reloadOnStaleChunk");
  });

  it("skips the reload once a navigation away has been announced", () => {
    mod.markNavigatingAway();

    const err = new Error("Failed to fetch dynamically imported module: /a.js");
    expect(mod.tryReloadOnStaleChunk(err)).toBe(false);
    expect(reload).not.toHaveBeenCalled();
    expect(sessionStorage.getItem("octop:chunk-reload")).toBeNull();
  });

  it("skips the reload after the browser fires pagehide", () => {
    mod.installChunkLoadRecovery();
    window.dispatchEvent(new Event("pagehide"));

    const err = new Error("Failed to fetch dynamically imported module: /a.js");
    expect(mod.tryReloadOnStaleChunk(err)).toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });

  it("recovers again when the page is restored from bfcache", () => {
    mod.installChunkLoadRecovery();
    window.dispatchEvent(new Event("pagehide"));
    window.dispatchEvent(new Event("pageshow"));

    const err = new Error("Failed to fetch dynamically imported module: /a.js");
    expect(mod.tryReloadOnStaleChunk(err)).toBe(true);
    expect(reload).toHaveBeenCalledOnce();
  });
});
