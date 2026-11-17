import { afterEach, describe, expect, it } from "vitest";
import { remotePluginUiUnavailable } from "./remotePluginUi";
import { clearToolPluginIndex, updateToolPluginIndex } from "./toolPluginIndex";
import type { InstalledPlugin } from "../../api/modules/plugins";

const weather = {
  id: "weather",
  tools: [{ name: "get_weather" }],
} as InstalledPlugin;

afterEach(() => {
  clearToolPluginIndex();
});

describe("remotePluginUiUnavailable", () => {
  it("stays quiet until the local plugin list has loaded", () => {
    expect(
      remotePluginUiUnavailable({
        agentId: "bridge:39CF56:FW1MED",
        toolName: "get_weather",
        hasOctopUi: true,
      }),
    ).toBe(false);
  });

  it("annotates a cloud expert tool this machine has not installed", () => {
    updateToolPluginIndex([]);
    expect(
      remotePluginUiUnavailable({
        agentId: "bridge:39CF56:FW1MED",
        toolName: "get_weather",
        hasOctopUi: true,
      }),
    ).toBe(true);
  });

  it("keeps the real card path when the same plugin is installed locally", () => {
    updateToolPluginIndex([weather]);
    expect(
      remotePluginUiUnavailable({
        agentId: "bridge:39CF56:FW1MED",
        toolName: "get_weather",
        hasOctopUi: true,
      }),
    ).toBe(false);
  });

  it("does not annotate local experts", () => {
    updateToolPluginIndex([]);
    expect(
      remotePluginUiUnavailable({
        agentId: "C10WX7",
        toolName: "get_weather",
        hasOctopUi: true,
      }),
    ).toBe(false);
  });
});
