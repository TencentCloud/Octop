import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { InstalledPlugin } from "../../api/modules/plugins";
import {
  isPluginUiLoaded,
  loadInstalledPluginUis,
  reloadPluginToolUis,
  resetPluginUiLoader,
} from "./loader";

vi.mock("./host", () => ({ createPluginUiHost: vi.fn(() => ({})) }));
vi.mock("./registry", () => ({ unregisterPluginRenderers: vi.fn() }));
vi.mock("../../api/config", () => ({
  getApiUrl: (path: string) => `/octop/api${path}`,
}));
vi.mock("../../api/request", () => ({ getAuthToken: () => "session-token" }));

const plugin: InstalledPlugin = {
  id: "theme",
  enabled: true,
  ui: { entry: "ui/index.js", manifest: "ui/manifest.json" },
};
let setup: ReturnType<typeof vi.fn>;
let cleanup: ReturnType<typeof vi.fn>;

beforeEach(() => {
  setup = vi.fn();
  cleanup = vi.fn();
  window.addEventListener("plugin-test:setup", setup);
  window.addEventListener("plugin-test:cleanup", cleanup);
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, text: async () => "" }),
  );
  vi.stubGlobal(
    "URL",
    Object.assign(class extends URL {}, {
      createObjectURL: vi.fn(
        () => new URL("./lifecycle.fixture.ts", import.meta.url).pathname,
      ),
      revokeObjectURL: vi.fn(),
    }),
  );
});

afterEach(() => {
  resetPluginUiLoader();
  window.removeEventListener("plugin-test:setup", setup);
  window.removeEventListener("plugin-test:cleanup", cleanup);
  vi.unstubAllGlobals();
});

describe("plugin UI lifecycle", () => {
  it("loads once for concurrent callers and cleans up when disabled", async () => {
    await Promise.all([
      loadInstalledPluginUis([plugin]),
      loadInstalledPluginUis([plugin]),
    ]);
    expect(setup).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledWith("/octop/api/plugins/theme/ui/index.js", {
      headers: { Authorization: "Bearer session-token" },
      signal: expect.any(AbortSignal),
    });
    await reloadPluginToolUis([{ ...plugin, enabled: false }]);
    expect(cleanup).toHaveBeenCalledTimes(1);
    expect(isPluginUiLoaded(plugin.id)).toBe(false);
    await loadInstalledPluginUis([plugin]);
    expect(setup).toHaveBeenCalledTimes(2);
    await reloadPluginToolUis([]);
    expect(cleanup).toHaveBeenCalledTimes(2);
    expect(isPluginUiLoaded(plugin.id)).toBe(false);
  });

  it("cleans up an async setup that resolves after the layout unmounts", async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      text: async () =>
        'export async function setup() { window.dispatchEvent(new Event("plugin-test:setup")); await window.__gate; return () => window.dispatchEvent(new Event("plugin-test:cleanup")); }',
    } as Response);
    (window as Window & { __gate?: Promise<void> }).__gate = gate;
    const loading = loadInstalledPluginUis([plugin]);
    await vi.waitFor(() => expect(setup).toHaveBeenCalledTimes(1));
    resetPluginUiLoader();
    release();
    await loading;
    expect(cleanup).toHaveBeenCalledTimes(1);
    expect(isPluginUiLoaded(plugin.id)).toBe(false);
  });

  it("unmounts once, cleans up once, then sets up once after signing in again", async () => {
    await loadInstalledPluginUis([plugin]);
    resetPluginUiLoader();
    expect(cleanup).toHaveBeenCalledTimes(1);
    expect(setup).toHaveBeenCalledTimes(1);
    await loadInstalledPluginUis([plugin]);
    expect(setup).toHaveBeenCalledTimes(2);
    expect(cleanup).toHaveBeenCalledTimes(1);
    resetPluginUiLoader();
    expect(cleanup).toHaveBeenCalledTimes(2);
  });

  it("does not activate an old load after the loader has been reset", async () => {
    let resolve!: (value: { ok: boolean; text: () => Promise<string> }) => void;
    vi.mocked(fetch).mockReturnValueOnce(
      new Promise<Response>((done) => {
        resolve = done as typeof resolve;
      }),
    );
    const loading = loadInstalledPluginUis([plugin]);
    resetPluginUiLoader();
    resolve({ ok: true, text: async () => "" });
    await loading;
    expect(setup).not.toHaveBeenCalled();
    expect(isPluginUiLoaded(plugin.id)).toBe(false);
  });
});
