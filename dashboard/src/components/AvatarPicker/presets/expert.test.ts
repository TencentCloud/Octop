import { describe, expect, it } from "vitest";

import { EXPERT_AVATAR_PRESETS, canonicalExpertPresetId } from "./expert";

const visible = new Set(EXPERT_AVATAR_PRESETS.map((preset) => preset.id));

describe("expert avatar presets", () => {
  it("collapses portraits that reuse another tile", () => {
    const aliases: Record<string, string> = {
      "scene-design": "general-assistant",
      "ai-coding-coach": "scene-tech",
      "scene-finance": "scene-office",
      "stock-assistant": "scene-office",
      "scene-legal": "scene-education",
      "scene-content-creation": "scene-marketing",
      "news-trend": "scene-marketing",
      "scene-media": "scene-marketing",
    };
    for (const [id, canonical] of Object.entries(aliases)) {
      expect(visible.has(id)).toBe(false);
      expect(canonicalExpertPresetId(id)).toBe(canonical);
      expect(visible.has(canonical)).toBe(true);
    }
  });
});
