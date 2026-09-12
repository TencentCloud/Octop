import { describe, expect, it } from "vitest";
import type { ChatMessage } from "../hooks/useChat";
import {
  buildPlanBriefFromMessages,
  formatPlanBrief,
  planBriefPreview,
  planContinueHandoff,
  planExecuteHandoff,
  stripConversationModeUiInstructions,
} from "./planArtifact";

describe("planArtifact (#616 P5/P7)", () => {
  it("formats brief with summary and todos", () => {
    const brief = formatPlanBrief({
      summary: "Ship modes.",
      todos: [{ id: "1", content: "Ask overlay", status: "completed" }],
    });
    expect(brief).toContain("Approved plan");
    expect(brief).toContain("Ship modes.");
    expect(brief).toContain("1. Ask overlay (completed)");
    expect(brief).toContain("Execute this plan now.");
  });

  it("planBriefPreview drops headers and truncates", () => {
    const brief = formatPlanBrief({
      summary: "Do the thing.",
      todos: [{ id: "1", content: "Step one", status: "pending" }],
    });
    const preview = planBriefPreview(brief);
    expect(preview).toContain("Do the thing.");
    expect(preview).toContain("Step one");
    expect(preview).not.toContain("Approved plan");
    expect(preview).not.toMatch(/Execute this plan now/i);
  });

  it("planExecuteHandoff switches to craft with silent planBrief metadata", () => {
    const handoff = planExecuteHandoff(formatPlanBrief({ summary: "Go." }));
    expect(handoff.conversationMode).toBe("craft");
    expect(handoff.hideUserMessage).toBe(true);
    expect(handoff.text).toBe("Execute the approved plan now.");
    expect(handoff.planBrief).toContain("Go.");
    expect(handoff.planBrief).toContain("Approved plan");
  });

  it("planContinueHandoff keeps plan mode (P8)", () => {
    expect(planContinueHandoff()).toEqual({ conversationMode: "plan" });
  });

  it("strips mode-switch UI instructions from assistant copy", () => {
    const raw = [
      "当前仍在计划模式，edit_file 等修改类工具不可用。",
      "",
      "需要你手动切换到默认（Craft / 做一做）模式后，我才能直接修 bug 和跑测试。",
      "",
      "切换入口：输入框旁边的模式选择按钮，从「计划」切回默认即可。",
      "",
      "脚本将用 awk 采集 CPU。",
    ].join("\n");
    const cleaned = stripConversationModeUiInstructions(raw);
    expect(cleaned).toContain("awk");
    expect(cleaned).not.toMatch(/手动切换/);
    expect(cleaned).not.toMatch(/模式选择按钮/);
    expect(
      stripConversationModeUiInstructions(
        [
          "当前仍在计划模式，edit_file 等修改类工具不可用。",
          "",
          "需要你手动切换到默认（Craft / 做一做）模式。",
          "",
          "切换入口：输入框旁边的模式选择按钮。",
        ].join("\n"),
      ),
    ).toBe("");
  });

  it("keeps ordinary mentions of chat input", () => {
    expect(
      stripConversationModeUiInstructions(
        "You can paste content into the chat input area.",
      ),
    ).toContain("chat input");
  });

  it("buildPlanBriefFromMessages merges assistant text and write_todos", () => {
    const messages: ChatMessage[] = [
      {
        id: "1",
        role: "user",
        content: "plan",
        status: "done",
        timestamp: 1,
      },
      {
        id: "2",
        role: "assistant",
        content: "",
        toolData: {
          name: "write_todos",
          arguments: JSON.stringify({
            todos: [{ id: "1", content: "Write tests", status: "pending" }],
          }),
        },
        status: "done",
        timestamp: 2,
      },
      {
        id: "3",
        role: "assistant",
        content: "Here is the plan.",
        status: "done",
        timestamp: 3,
      },
    ];
    const brief = buildPlanBriefFromMessages(messages);
    expect(brief).toContain("Here is the plan.");
    expect(brief).toContain("Write tests");
  });

  it("buildPlanBriefFromMessages ignores short replies without todos", () => {
    const messages: ChatMessage[] = [
      {
        id: "1",
        role: "user",
        content: "plan",
        status: "done",
        timestamp: 1,
      },
      {
        id: "2",
        role: "assistant",
        content: "好的，我先想想。",
        status: "done",
        timestamp: 2,
      },
    ];
    expect(buildPlanBriefFromMessages(messages)).toBeNull();
  });

  it("buildPlanBriefFromMessages ignores stale write_todos from earlier turns", () => {
    const messages: ChatMessage[] = [
      {
        id: "1",
        role: "user",
        content: "plan a file",
        status: "done",
        timestamp: 1,
      },
      {
        id: "2",
        role: "assistant",
        content: "",
        toolData: {
          name: "write_todos",
          arguments: JSON.stringify({
            todos: [{ id: "1", content: "Write tests", status: "pending" }],
          }),
        },
        status: "done",
        timestamp: 2,
      },
      {
        id: "3",
        role: "assistant",
        content:
          "Here is a detailed plan with plenty of substance for the card.",
        status: "done",
        timestamp: 3,
      },
      {
        id: "4",
        role: "user",
        content: "嗯",
        status: "done",
        timestamp: 4,
      },
      {
        id: "5",
        role: "assistant",
        content: "好的",
        status: "done",
        timestamp: 5,
      },
    ];
    expect(buildPlanBriefFromMessages(messages)).toBeNull();
  });
});
