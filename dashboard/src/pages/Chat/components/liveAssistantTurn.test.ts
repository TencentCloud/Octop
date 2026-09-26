import { describe, expect, it } from "vitest";
import { isLiveAssistantTurn } from "./liveAssistantTurn";

describe("isLiveAssistantTurn", () => {
  it("is true for the assistant group after the latest user message", () => {
    expect(
      isLiveAssistantTurn({
        isStreaming: true,
        groupIndex: 3,
        lastAssistantGroupIndex: 3,
        lastUserGroupIndex: 2,
      }),
    ).toBe(true);
  });

  it("is false for the previous assistant turn after the user just sent", () => {
    // groups: … assistant(1), user(2) — last assistant is still 1
    expect(
      isLiveAssistantTurn({
        isStreaming: true,
        groupIndex: 1,
        lastAssistantGroupIndex: 1,
        lastUserGroupIndex: 2,
      }),
    ).toBe(false);
  });

  it("is false when not streaming", () => {
    expect(
      isLiveAssistantTurn({
        isStreaming: false,
        groupIndex: 3,
        lastAssistantGroupIndex: 3,
        lastUserGroupIndex: 2,
      }),
    ).toBe(false);
  });

  it("keeps earlier team speakers live while a later one is also streaming", () => {
    expect(
      isLiveAssistantTurn({
        isStreaming: true,
        groupIndex: 1,
        lastAssistantGroupIndex: 3,
        lastUserGroupIndex: 0,
      }),
    ).toBe(true);
  });
});
