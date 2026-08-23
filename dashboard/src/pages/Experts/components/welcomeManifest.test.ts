import { describe, expect, it } from "vitest";

import {
  filterQuickPrompts,
  mergeWelcomeIntoManifest,
  parseManifestObject,
  shouldWriteWelcomeManifest,
} from "./welcomeManifest";
import type { QuickPrompt } from "./welcomeManifest";

const prompt = (over: Partial<QuickPrompt> = {}): QuickPrompt => ({
  title: { zh: "标题", en: "Title" },
  description: { zh: "描述", en: "Desc" },
  prompt: { zh: "提示", en: "Prompt" },
  color: "#e8f4ff",
  icon_name: "sparkles",
  ...over,
});

describe("shouldWriteWelcomeManifest", () => {
  it("writes only after a successful load when the editor is dirty", () => {
    expect(shouldWriteWelcomeManifest("ready", true)).toBe(true);
    expect(shouldWriteWelcomeManifest("ready", false)).toBe(false);
    expect(shouldWriteWelcomeManifest("loading", true)).toBe(false);
    expect(shouldWriteWelcomeManifest("error", true)).toBe(false);
  });
});

describe("parseManifestObject", () => {
  it("accepts empty content as a new object", () => {
    expect(parseManifestObject("")).toEqual({ ok: true, value: {} });
    expect(parseManifestObject("   ")).toEqual({ ok: true, value: {} });
  });

  it("parses a JSON object", () => {
    expect(parseManifestObject('{"id":"demo","label":{"zh":"A"}}')).toEqual({
      ok: true,
      value: { id: "demo", label: { zh: "A" } },
    });
  });

  it("rejects arrays, scalars, and invalid JSON", () => {
    expect(parseManifestObject("[]")).toEqual({ ok: false });
    expect(parseManifestObject('"x"')).toEqual({ ok: false });
    expect(parseManifestObject("{")).toEqual({ ok: false });
  });
});

describe("mergeWelcomeIntoManifest", () => {
  it("keeps unrelated keys and updates only welcome fields", () => {
    const merged = mergeWelcomeIntoManifest(
      {
        id: "demo",
        label: { zh: "演示", en: "Demo" },
        source: { type: "skillhub" },
        welcome_message: { zh: "旧中文", en: "Old English" },
        quick_prompts: [],
      },
      {
        welcome_message: { zh: "新中文", en: "Old English" },
        quick_prompts: [prompt({ title: { zh: "卡", en: "" } })],
      },
    );
    expect(merged.id).toBe("demo");
    expect(merged.label).toEqual({ zh: "演示", en: "Demo" });
    expect(merged.source).toEqual({ type: "skillhub" });
    expect(merged.welcome_message).toEqual({ zh: "新中文", en: "Old English" });
    expect(merged.quick_prompts).toEqual([
      prompt({ title: { zh: "卡", en: "" } }),
    ]);
  });

  it("drops empty welcome copy and empty prompt cards", () => {
    const merged = mergeWelcomeIntoManifest(
      { id: "demo", welcome_message: { zh: "hi", en: "hi" } },
      {
        welcome_message: { zh: "  ", en: "" },
        quick_prompts: [
          prompt({ title: { zh: "", en: "" }, prompt: { zh: "", en: "" } }),
        ],
      },
    );
    expect(merged).toEqual({ id: "demo", quick_prompts: [] });
  });

  it("leaves welcome copy unchanged when the patch omits it", () => {
    const merged = mergeWelcomeIntoManifest(
      {
        id: "demo",
        welcome_message: { zh: "你好", en: "Hi" },
      },
      { quick_prompts: [prompt()] },
    );
    expect(merged.welcome_message).toEqual({ zh: "你好", en: "Hi" });
    expect(merged.quick_prompts).toEqual([prompt()]);
  });
});

describe("filterQuickPrompts", () => {
  it("keeps a card that has either title or prompt text", () => {
    expect(
      filterQuickPrompts([
        prompt({ title: { zh: "", en: "" }, prompt: { zh: "x", en: "" } }),
        prompt({ title: { zh: "", en: "" }, prompt: { zh: "", en: "" } }),
      ]),
    ).toHaveLength(1);
  });
});
