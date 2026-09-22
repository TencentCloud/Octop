import { act, renderHook } from "@testing-library/react";
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
  it("lists enabled skills with friendly labels and skips reserved slash names", () => {
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
      "✦ Web Search",
    ]);
    const skillItem = result.current.slashMenuItems.find(
      (item) => item.spec.name === "web-search",
    );
    expect(skillItem?.label).toBe("Web Search");
    expect(skillItem?.spec.usage).toBe("✦ Web Search <task>");
    expect(skillItem?.spec.category).toBe("skills");
    // Shortcut popover keeps slash commands only; skills use the skill picker.
    expect(
      result.current.slashPickerGroups.map((group) => group.category),
    ).toEqual(["core"]);
    expect(
      result.current.slashPickerGroups.flatMap((group) =>
        group.items.map((item) => item.command),
      ),
    ).toEqual(["/stop"]);
  });
});

describe("useSlashMentionInput workspace files", () => {
  it("keeps empty @ as a hint-only file section and inserts the workspace path", () => {
    const setText = vi.fn();
    const { result } = renderHook(() =>
      useSlashMentionInput({
        text: "@",
        setText,
        textareaRef: { current: null },
        slashCommands: [stopCommand],
        labelFor: (spec) => spec.label_en,
        locale: "en",
        availableExperts: [],
        selectedConnectors: [],
        agentId: "A1",
        onSend: vi.fn(),
        onNewChat: vi.fn(),
        onCancel: vi.fn(),
        isStreaming: false,
        onSubmitRef: { current: vi.fn() },
      }),
    );

    expect(result.current.mentionItems).toEqual([]);

    act(() => {
      result.current.handleTextChange("@");
    });
    act(() => {
      result.current.handleMentionSelect({
        kind: "file",
        path: "docs/api.md",
        label: "api.md",
      });
    });

    expect(setText).toHaveBeenCalledWith("@docs/api.md ");
  });

  it("keeps spaces in the workspace path and does not toggle an existing cite", () => {
    const setText = vi.fn();
    const { result } = renderHook(() =>
      useSlashMentionInput({
        text: "@docs/api.md @note",
        setText,
        textareaRef: { current: null },
        slashCommands: [stopCommand],
        labelFor: (spec) => spec.label_en,
        locale: "en",
        availableExperts: [],
        selectedConnectors: [],
        agentId: "A1",
        onSend: vi.fn(),
        onNewChat: vi.fn(),
        onCancel: vi.fn(),
        isStreaming: false,
        onSubmitRef: { current: vi.fn() },
      }),
    );

    act(() => {
      result.current.handleTextChange("@docs/api.md @note");
    });
    act(() => {
      result.current.handleMentionSelect({
        kind: "file",
        path: "notes/my file.md",
        label: "my file.md",
      });
    });

    expect(setText).toHaveBeenCalledWith("@docs/api.md @notes/my file.md ");
  });
});
