import { beforeEach, describe, expect, it } from "vitest";
import {
  clearPluginPages,
  listPluginPages,
  parsePluginPageManifest,
  registerPluginPage,
  resolvePluginPage,
  unregisterPluginPages,
} from "./registry";

const component = () => null;

beforeEach(clearPluginPages);

describe("standalone plugin pages", () => {
  it("accepts legacy tool manifests without declaring pages", () => {
    expect(parsePluginPageManifest({ renderers: [{ id: "legacy" }] })).toEqual(
      [],
    );
  });

  it("validates declared page IDs before constructing a route", () => {
    expect(
      parsePluginPageManifest({
        pages: [{ id: "settings", title: "Settings" }],
      }),
    ).toEqual([{ id: "settings", title: "Settings" }]);
    for (const id of ["../settings", "settings/page", "", "has space"]) {
      expect(() =>
        parsePluginPageManifest({ pages: [{ id, title: "Settings" }] }),
      ).toThrow();
    }
    expect(() =>
      parsePluginPageManifest({
        pages: [
          { id: "settings", title: "Settings" },
          { id: "settings", title: "Duplicate" },
        ],
      }),
    ).toThrow();
  });

  it("keeps a page scoped to its owning plugin and rejects unknown pages", () => {
    registerPluginPage({
      pluginId: "one",
      id: "settings",
      title: "One",
      component,
    });
    registerPluginPage({
      pluginId: "two",
      id: "settings",
      title: "Two",
      component,
    });
    expect(resolvePluginPage("one", "settings")?.title).toBe("One");
    expect(resolvePluginPage("two", "settings")?.title).toBe("Two");
    expect(resolvePluginPage("one", "unknown")).toBeNull();
  });

  it("removes all pages for a disabled or uninstalled plugin without affecting another", () => {
    registerPluginPage({
      pluginId: "one",
      id: "settings",
      title: "One",
      component,
    });
    registerPluginPage({
      pluginId: "two",
      id: "settings",
      title: "Two",
      component,
    });
    unregisterPluginPages("one");
    expect(resolvePluginPage("one", "settings")).toBeNull();
    expect(listPluginPages().map((page) => page.pluginId)).toEqual(["two"]);
  });
});
