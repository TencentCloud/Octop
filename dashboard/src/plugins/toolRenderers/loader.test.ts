import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { InstalledPlugin } from "../../api/modules/plugins";
import type { OctopPluginUIHost } from "./types";
import {
  isPluginUiLoaded,
  loadInstalledPluginUis,
  reloadPluginToolUis,
  resetPluginUiLoader,
} from "./loader";
import { clearPluginPages, listPluginPages } from "../pages/registry";
import { clearToolRenderers, listRegisteredRenderers } from "./registry";

vi.mock("../../api/config", () => ({
  getApiUrl: (path: string) => `/api${path}`,
}));
vi.mock("../../api/request", () => ({
  request: vi.fn(),
  getAuthToken: () => "test-token",
}));
vi.mock("../../i18n", () => ({ default: { language: "en" } }));
vi.mock("../../pages/Chat/hooks/chatStore", () => ({
  patchToolResultData: vi.fn(),
}));

const installed: InstalledPlugin = {
  id: "sample",
  version: "1",
  enabled: true,
  ui: { entry: "ui/index.js", manifest: "ui/manifest.json" },
};
const source =
  "export function setup(host) { globalThis.__octopPluginTestSetup(host); }";
const manifest = JSON.stringify({
  pages: [{ id: "welcome", title: "Welcome" }],
});
const component = () => null;
const setup = vi.fn<(host: OctopPluginUIHost) => void>();
const fetchMock = vi.fn<typeof fetch>();
const revoke = vi.fn();
const BrowserURL = URL;
let serial = 0;

function response(body: string): Response {
  return { ok: true, status: 200, text: async () => body } as Response;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

beforeEach(() => {
  clearPluginPages();
  clearToolRenderers();
  setup.mockReset().mockImplementation((host) => {
    host.registerRenderer({ id: "legacy", tools: ["legacy_tool"], component });
    host.registerPage({ id: "welcome", component });
  });
  fetchMock
    .mockReset()
    .mockImplementation(async (url) =>
      response(String(url).endsWith("manifest.json") ? manifest : source),
    );
  revoke.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("__octopPluginTestSetup", setup);
  // Exercise the actual dynamic ESM import; Node cannot import browser blob URLs.
  vi.stubGlobal(
    "URL",
    class extends BrowserURL {
      static createObjectURL() {
        return `data:text/javascript,${encodeURIComponent(
          `${source}\n// ${serial++}`,
        )}`;
      }
      static revokeObjectURL = revoke;
    },
  );
});

afterEach(() => {
  resetPluginUiLoader();
  vi.unstubAllGlobals();
});

it("clears an uninstalled plugin and loads the same ID when reinstalled", async () => {
  await loadInstalledPluginUis([installed]);
  expect(listPluginPages()).toHaveLength(1);
  await loadInstalledPluginUis([]);
  expect(isPluginUiLoaded(installed.id)).toBe(false);
  await loadInstalledPluginUis([installed]);
  expect(listPluginPages()).toHaveLength(1);
  expect(setup).toHaveBeenCalledTimes(2);
});

it("does not resurrect a disabled page when an old entry fetch completes", async () => {
  const entry = deferred<Response>();
  const requested = deferred<void>();
  fetchMock.mockImplementation(async (url) => {
    if (String(url).endsWith("manifest.json")) return response(manifest);
    requested.resolve();
    return entry.promise;
  });
  const oldLoad = loadInstalledPluginUis([installed]);
  await requested.promise;
  // The replacement's entry is available immediately; only the old request waits.
  fetchMock.mockImplementation(async () => response(source));
  await reloadPluginToolUis([{ ...installed, enabled: false }]);
  entry.resolve(response(source));
  await oldLoad;
  expect(listPluginPages()).toEqual([]);
  expect(setup).toHaveBeenCalledTimes(1);
  expect(listRegisteredRenderers()).toHaveLength(1);
});

it("deduplicates concurrent loads from the same plugin snapshot", async () => {
  await Promise.all([
    loadInstalledPluginUis([installed]),
    loadInstalledPluginUis([installed]),
  ]);
  expect(setup).toHaveBeenCalledTimes(1);
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

it("invalidates a retained setup host after uninstall", async () => {
  await loadInstalledPluginUis([installed]);
  const host = setup.mock.calls[0][0];
  await loadInstalledPluginUis([]);
  host.registerPage({ id: "welcome", component });
  host.registerRenderer({ id: "late", component });
  expect(listPluginPages()).toEqual([]);
  expect(listRegisteredRenderers()).toEqual([]);
});

it("reloads version or UI metadata changes without an explicit reset", async () => {
  await loadInstalledPluginUis([installed]);
  await loadInstalledPluginUis([{ ...installed, version: "2" }]);
  await loadInstalledPluginUis([
    {
      ...installed,
      version: "2",
      ui: { ...installed.ui!, entry: "ui/updated.js" },
    },
  ]);
  expect(setup).toHaveBeenCalledTimes(3);
});

it.each([
  { ...installed, error: "unavailable" },
  { ...installed, ui: null },
])(
  "removes registrations when a plugin loses its usable UI",
  async (unavailable) => {
    await loadInstalledPluginUis([installed]);
    await loadInstalledPluginUis([unavailable]);
    expect(listPluginPages()).toEqual([]);
    expect(listRegisteredRenderers()).toEqual([]);
    expect(isPluginUiLoaded(installed.id)).toBe(false);
  },
);

it("keeps renderer-only legacy modules and authenticated asset requests", async () => {
  fetchMock.mockImplementation(async (url) =>
    response(
      String(url).endsWith("manifest.json") ? '{"renderers":[]}' : source,
    ),
  );
  setup.mockImplementation((host) =>
    host.registerRenderer({ id: "legacy", component }),
  );
  await loadInstalledPluginUis([installed]);
  expect(isPluginUiLoaded(installed.id)).toBe(true);
  expect(listPluginPages()).toEqual([]);
  expect(listRegisteredRenderers()).toHaveLength(1);
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/plugins/sample/ui/manifest.json",
    {
      headers: { Authorization: "Bearer test-token" },
    },
  );
  resetPluginUiLoader();
  expect(revoke).toHaveBeenCalledTimes(1);
});
