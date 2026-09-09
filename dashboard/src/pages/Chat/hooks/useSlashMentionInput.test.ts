import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { SlashCommandSpec } from "../../../api/modules/slash";
import type { SkillSpec } from "../../Agent/Skills/useSkills";
import { useSlashMentionInput } from "./useSlashMentionInput";

const stopCommand: SlashCommandSpec = {
  name: "stop",
  command: "/stop",
  aliases: [],
  label_en: "Stop",
  label_zh: "停止",
  description_en: "",
  description_zh: "",
  usage: "/stop",
  icon: "Square",
  tone: "red",
  category: "core",
  origins: ["ui"],
  client_action: "cancel_stream",
};

function skill(over: Partial<SkillSpec> = {}): SkillSpec {
  return {
    slug: "web-search",
    name: "Web Search",
    description: "Search",
    enabled: true,
    kind: "builtin",
    ...over,
  };
}

describe("useSlashMentionInput skills", () => {
  it("lists enabled skills as /slug items and skips reserved slash names", () => {
    const { result } = renderHook(() =>
      useSlashMentionInput({
        text: "",
        setText: vi.fn(),
        textareaRef: { current: null },
        slashCommands: [stopCommand],
        labelFor: (spec) => spec.label_en,
        locale: "en",
        availableSkills: [
          skill(),
          skill({ slug: "stop", name: "Stop skill", enabled: true }),
          skill({ slug: "off", name: "Off", enabled: false }),
        ],
        availableExperts: [],
        selectedConnectors: [],
        onSend: vi.fn(),
        onNewChat: vi.fn(),
        onCancel: vi.fn(),
        isStreaming: false,
        onSubmitRef: { current: vi.fn() },
      }),
    );

    expect(result.current.slashMenuItems.map((item) => item.command)).toEqual([
      "/stop",
      "/web-search",
    ]);
    const skillItem = result.current.slashMenuItems.find(
      (item) => item.command === "/web-search",
    );
    expect(skillItem?.spec.usage).toBe("/web-search <task>");
    expect(skillItem?.spec.category).toBe("skills");
  });
});
