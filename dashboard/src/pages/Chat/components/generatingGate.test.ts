import { describe, expect, it } from "vitest";
import { chatGeneratingPhase, shouldShowGenerating } from "./generatingGate";

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
});

describe("chatGeneratingPhase", () => {
  it("shows footer while streaming and elapsed while awaiting first assistant", () => {
    expect(
      chatGeneratingPhase({
        isStreaming: true,
        loading: false,
        lastMessageRole: "user",
      }),
    ).toEqual({ showFooter: true, showElapsed: true });
  });

  it("hides elapsed once an assistant bubble exists", () => {
    expect(
      chatGeneratingPhase({
        isStreaming: true,
        lastMessageRole: "assistant",
      }),
    ).toEqual({ showFooter: true, showElapsed: false });
  });

  it("hides footer during initial history load", () => {
    expect(
      chatGeneratingPhase({
        isStreaming: true,
        loading: true,
        lastMessageRole: "user",
      }),
    ).toEqual({ showFooter: false, showElapsed: false });
  });
});
