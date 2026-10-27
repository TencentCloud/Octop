import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { OctopPluginUIHost } from "./types";

const source = readFileSync(
  resolve(process.cwd(), "../plugins/simple-theme/ui/index.js"),
  "utf8",
);
const setup = new Function(
  source.replace("export function setup", "return function setup"),
)() as (host: OctopPluginUIHost) => () => void;
let cleanup: (() => void) | undefined;
let fonts: Set<unknown>;

function host() {
  return {
    registerRenderer: vi.fn(),
    request: vi.fn().mockResolvedValue([]),
    requestBlob: vi.fn().mockResolvedValue({
      arrayBuffer: async () => new ArrayBuffer(0),
    }),
  };
}

beforeEach(() => {
  vi.useFakeTimers();
  document.documentElement.id = "existing-root";
  document.head.innerHTML =
    '<meta name="theme-color" content="#123456" media="(prefers-color-scheme: dark)">';
  document.body.innerHTML = "";
  fonts = new Set();
  Object.defineProperty(document, "fonts", {
    configurable: true,
    value: fonts,
  });
  vi.stubGlobal(
    "FontFace",
    class {
      async load() {
        return this;
      }
    },
  );
});

afterEach(() => {
  cleanup?.();
  cleanup = undefined;
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("simple theme UI lifecycle", () => {
  it("restores styles, metadata, fonts and listeners, then supports enabling again", async () => {
    const api = host();
    cleanup = setup(api as unknown as OctopPluginUIHost);
    await vi.advanceTimersByTimeAsync(0);
    expect(document.documentElement.id).toBe("octop-simple-theme-root");
    expect(api.requestBlob).toHaveBeenCalledWith(
      "/plugins/simple-theme/ui/fonts/InterVariable.woff2",
      { signal: expect.any(AbortSignal) },
    );
    expect(fonts.size).toBe(1);
    document.documentElement.setAttribute("data-theme", "dark");
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute("content", "#1a1c28");
    await vi.advanceTimersByTimeAsync(0);
    cleanup();
    expect(document.getElementById("octop-simple-theme-style")).toBeNull();
    expect(document.documentElement.id).toBe("existing-root");
    expect(
      document.querySelector('meta[name="theme-color"]')?.outerHTML,
    ).toContain("#1a1c28");
    expect(
      document.querySelector('meta[name="theme-color"]')?.getAttribute("media"),
    ).toBe("(prefers-color-scheme: dark)");
    expect(fonts.size).toBe(0);
    document.dispatchEvent(
      new KeyboardEvent("keydown", { key: "d", ctrlKey: true, altKey: true }),
    );
    window.dispatchEvent(new Event("resize"));
    await vi.advanceTimersByTimeAsync(1000);
    expect(document.getElementById("simple-diag")).toBeNull();
    expect(document.getElementById("octop-simple-theme-style")).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
    cleanup = setup(api as unknown as OctopPluginUIHost);
    expect(document.getElementById("octop-simple-theme-style")).not.toBeNull();
  });

  it("does not add a font after being disabled during its request", async () => {
    let resolve!: (blob: Blob) => void;
    const api = host();
    api.requestBlob.mockReturnValue(
      new Promise<Blob>((done) => {
        resolve = done;
      }),
    );
    cleanup = setup(api as unknown as OctopPluginUIHost);
    const signal = api.requestBlob.mock.calls[0][1].signal as AbortSignal;
    cleanup();
    expect(signal.aborted).toBe(true);
    resolve({ arrayBuffer: async () => new ArrayBuffer(0) } as Blob);
    await vi.advanceTimersByTimeAsync(0);
    expect(fonts.size).toBe(0);
    expect(document.getElementById("octop-simple-theme-style")).toBeNull();
  });
});
