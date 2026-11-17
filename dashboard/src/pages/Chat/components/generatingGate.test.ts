import { describe, expect, it } from "vitest";
import {
  awaitingVisibleAssistantReply,
  chatGeneratingPhase,
  shouldShowGenerating,
} from "./generatingGate";

describe("shouldShowGenerating", () => {
  it("is true while streaming and not loading history", () => {
    expect(shouldShowGenerating({ isStreaming: true, loading: false })).toBe(
      true,
    );
  });

  it("is false when not streaming", () => {
    expect(shouldShowGenerating({ isStreaming: false })).toBe(false);
  });

  it("is false while the initial history spinner is up", () => {
    expect(shouldShowGenerating({ isStreaming: true, loading: true })).toBe(
      false,
    );
  });

  it("stays true for late team members after the host unlocks the composer", () => {
    expect(
      shouldShowGenerating({
        isStreaming: false,
        hasLiveSpeakers: true,
      }),
    ).toBe(true);
  });
});

describe("chatGeneratingPhase", () => {
  it("shows footer while streaming and elapsed while awaiting first assistant", () => {
    expect(
      chatGeneratingPhase({
        isStreaming: true,
        loading: false,
        lastMessageRole: "user",
      }),
    ).toEqual({
      showFooter: true,
      showElapsed: true,
      membersOnly: false,
    });
  });

  it("hides elapsed once an assistant bubble exists", () => {
    expect(
      chatGeneratingPhase({
        isStreaming: true,
        lastMessageRole: "assistant",
      }),
    ).toEqual({
      showFooter: true,
      showElapsed: false,
      membersOnly: false,
    });
  });

  it("hides footer during initial history load", () => {
    expect(
      chatGeneratingPhase({
        isStreaming: true,
        loading: true,
        lastMessageRole: "user",
      }),
    ).toEqual({
      showFooter: false,
      showElapsed: false,
      membersOnly: false,
    });
  });

  it("keeps the elapsed wait through a decision-only placeholder", () => {
    expect(
      chatGeneratingPhase({
        isStreaming: true,
        lastMessageRole: "assistant",
        awaitingVisibleReply: true,
      }),
    ).toEqual({
      showFooter: true,
      showElapsed: true,
      membersOnly: false,
    });
  });

  it("shows a members-only footer without cancel-phase elapsed", () => {
    expect(
      chatGeneratingPhase({
        isStreaming: false,
        hasLiveSpeakers: true,
        lastMessageRole: "assistant",
      }),
    ).toEqual({
      showFooter: true,
      showElapsed: false,
      membersOnly: true,
    });
  });
});

describe("awaitingVisibleAssistantReply", () => {
  it("stays open for a decision stamp with no text or tool", () => {
    expect(
      awaitingVisibleAssistantReply([
        { role: "user", content: "查一下磁盘" },
        { role: "assistant", content: "", status: "streaming" },
      ]),
    ).toBe(true);
  });

  it("closes once a tool or answer is visible", () => {
    expect(
      awaitingVisibleAssistantReply([
        { role: "user", content: "查一下磁盘" },
        { role: "assistant", content: "", toolData: { name: "execute" } },
      ]),
    ).toBe(false);
    expect(
      awaitingVisibleAssistantReply([
        { role: "user", content: "查一下磁盘" },
        { role: "assistant", content: "磁盘正常" },
      ]),
    ).toBe(false);
  });
});
