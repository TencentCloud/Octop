import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  bustServiceWorkerAndReload,
  clearChunkReloadFlag,
  isChunkLoadError,
  isStylesheetAssetLink,
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

  it("matches Firefox dynamic import failures", () => {
    expect(
      isChunkLoadError(
        new TypeError(
          "error loading dynamically imported module: https://x/assets/vendor-markdown.js",
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

describe("isStylesheetAssetLink", () => {
  it("accepts stylesheet links under /assets/", () => {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "https://example.com/assets/index.abc.css";
    expect(isStylesheetAssetLink(link)).toBe(true);
  });

  it("rejects modulepreload asset links (Firefox false positives)", () => {
    const link = document.createElement("link");
    link.rel = "modulepreload";
    link.href = "https://example.com/assets/vendor-markdown.abc.js";
    expect(isStylesheetAssetLink(link)).toBe(false);
  });
});

function stubReload() {
  const reload = vi.fn();
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { reload },
  });
  return reload;
}

describe("tryReloadOnStaleChunk", () => {
  let reload: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    sessionStorage.clear();
    reload = stubReload();
    clearChunkReloadFlag();
  });

  afterEach(() => {
    clearChunkReloadFlag();
  });

  it("reloads once on chunk error", async () => {
    const err = new Error("Failed to fetch dynamically imported module: /a.js");
    expect(tryReloadOnStaleChunk(err)).toBe(true);
    await vi.waitFor(() => expect(reload).toHaveBeenCalledOnce());
    expect(sessionStorage.getItem("octop:chunk-reload")).toBe("1");
  });

  it("does not loop on a second consecutive chunk error", async () => {
    const err = new Error("Failed to fetch dynamically imported module: /a.js");
    expect(tryReloadOnStaleChunk(err)).toBe(true);
    await vi.waitFor(() => expect(reload).toHaveBeenCalledOnce());
    reload.mockClear();

    // New document after reload: in-memory guard resets; session flag remains.
    vi.resetModules();
    const mod = await import("./reloadOnStaleChunk");
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { reload },
    });

    expect(mod.tryReloadOnStaleChunk(err)).toBe(false);
    expect(reload).not.toHaveBeenCalled();
    expect(sessionStorage.getItem("octop:chunk-reload")).toBeNull();
  });

  it("ignores concurrent chunk errors without clearing the one-shot flag", async () => {
    const err = new Error("Failed to fetch dynamically imported module: /a.js");
    expect(tryReloadOnStaleChunk(err)).toBe(true);
    expect(tryReloadOnStaleChunk(err)).toBe(true);
    await vi.waitFor(() => expect(reload).toHaveBeenCalledOnce());
    expect(sessionStorage.getItem("octop:chunk-reload")).toBe("1");
  });

  it("ignores non-chunk errors", () => {
    expect(tryReloadOnStaleChunk(new Error("boom"))).toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });
});

describe("bustServiceWorkerAndReload", () => {
  it("unregisters workers and drops caches before reloading", async () => {
    const reload = stubReload();
    const unregister = vi.fn().mockResolvedValue(true);
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: {
        getRegistrations: vi.fn().mockResolvedValue([{ unregister }]),
      },
    });
    const cachesDelete = vi.fn().mockResolvedValue(true);
    Object.defineProperty(window, "caches", {
      configurable: true,
      value: {
        keys: vi.fn().mockResolvedValue(["workbox-precache"]),
        delete: cachesDelete,
      },
    });

    await bustServiceWorkerAndReload();

    expect(unregister).toHaveBeenCalledOnce();
    expect(cachesDelete).toHaveBeenCalledWith("workbox-precache");
    expect(reload).toHaveBeenCalledOnce();
  });
});

describe("index.html boot recover", () => {
  it("embeds a classic script that shares the chunk-reload flag", () => {
    const html = readFileSync(resolve(__dirname, "../../index.html"), "utf8");
    expect(html).toContain('var KEY = "octop:chunk-reload"');
    expect(html).toContain("serviceWorker");
    expect(html).toContain("isStylesheetLink");
    expect(html).toContain("modulepreload");
    expect(html).not.toMatch(/<script type="module">[\s\S]*octop:chunk-reload/);
  });

  it("does not recover on arbitrary LINK asset errors", () => {
    const html = readFileSync(resolve(__dirname, "../../index.html"), "utf8");
    expect(html).not.toMatch(
      /t\.tagName === "LINK" && isAsset\(t\.href\)\) recover\(\)/,
    );
    expect(html).toContain("isStylesheetLink(t) && isAsset(t.href)");
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

  it("recovers again when the page is restored from bfcache", async () => {
    mod.installChunkLoadRecovery();
    window.dispatchEvent(new Event("pagehide"));
    window.dispatchEvent(new Event("pageshow"));

    const err = new Error("Failed to fetch dynamically imported module: /a.js");
    expect(mod.tryReloadOnStaleChunk(err)).toBe(true);
    await vi.waitFor(() => expect(reload).toHaveBeenCalledOnce());
  });
});
