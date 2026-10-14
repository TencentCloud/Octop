import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPluginUiHost } from "../toolRenderers/host";
import {
  clearPluginPages,
  listPluginPages,
  resolvePluginPage,
} from "./registry";
import {
  clearToolRenderers,
  resolveToolRenderer,
} from "../toolRenderers/registry";

vi.mock("../../api/request", () => ({ request: vi.fn() }));
vi.mock("../../i18n", () => ({ default: { language: "en" } }));
vi.mock("../../pages/Chat/hooks/chatStore", () => ({
  patchToolResultData: vi.fn(),
}));

const component = () => null;
beforeEach(() => {
  clearPluginPages();
  clearToolRenderers();
});

describe("public plugin page setup host", () => {
  it("requires the page declaration and scopes ownership to the installed plugin", () => {
    const host = createPluginUiHost("sample", [
      { id: "welcome", title: "Welcome" },
    ]);
    expect(() => host.registerPage({ id: "other", component })).toThrow(
      /declared/,
    );
    host.registerPage({ id: "welcome", component });
    expect(resolvePluginPage("sample", "welcome")?.component).toBe(component);
    expect(resolvePluginPage("another", "welcome")).toBeNull();
  });

  it("does not register disabled pages while retaining the legacy tool UI API", () => {
    const host = createPluginUiHost(
      "sample",
      [{ id: "welcome", title: "Welcome" }],
      false,
    );
    host.registerPage({ id: "welcome", component });
    expect(listPluginPages()).toEqual([]);
    host.registerRenderer({ id: "legacy", tools: ["legacy_tool"], component });
    expect(
      resolveToolRenderer({
        toolName: "legacy_tool",
        parsed: { isJson: false, raw: "text" },
      })?.id,
    ).toBe("legacy");
  });
});
