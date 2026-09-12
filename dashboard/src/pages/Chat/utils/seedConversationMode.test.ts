import { describe, expect, it } from "vitest";
import { PENDING_THREAD_ID } from "../constants";
import { resolveSeedConversationMode } from "./seedConversationMode";

describe("resolveSeedConversationMode", () => {
  it("reseeds agent default on empty new-chat composer", () => {
    expect(
      resolveSeedConversationMode({
        activeThreadId: null,
        previousThreadId: "thr_old",
        agentDefault: "craft",
        currentComposerMode: "plan",
      }),
    ).toEqual({ action: "set", mode: "craft" });
  });

  it("restores per-thread override when present", () => {
    expect(
      resolveSeedConversationMode({
        activeThreadId: "thr_a",
        previousThreadId: "thr_b",
        override: "ask",
        agentDefault: "craft",
        currentComposerMode: "plan",
      }),
    ).toEqual({ action: "set", mode: "ask" });
  });

  it("stamps composer mode when empty chat gets a real thread id", () => {
    expect(
      resolveSeedConversationMode({
        activeThreadId: "thr_new",
        previousThreadId: null,
        agentDefault: "ask",
        currentComposerMode: "plan",
      }),
    ).toEqual({ action: "stamp-override", mode: "plan" });
  });

  it("stamps composer mode when pending chat resolves to a real thread id", () => {
    expect(
      resolveSeedConversationMode({
        activeThreadId: "thr_new",
        previousThreadId: PENDING_THREAD_ID,
        agentDefault: "craft",
        currentComposerMode: "plan",
      }),
    ).toEqual({ action: "stamp-override", mode: "plan" });
  });

  it("ignores stale pending override and stamps current composer mode", () => {
    expect(
      resolveSeedConversationMode({
        activeThreadId: PENDING_THREAD_ID,
        previousThreadId: null,
        override: "plan",
        agentDefault: "craft",
        currentComposerMode: "ask",
      }),
    ).toEqual({ action: "stamp-override", mode: "ask" });
  });

  it("reseeds agent default when switching between existing threads", () => {
    expect(
      resolveSeedConversationMode({
        activeThreadId: "thr_b",
        previousThreadId: "thr_a",
        agentDefault: "craft",
        currentComposerMode: "plan",
      }),
    ).toEqual({ action: "set", mode: "craft" });
  });
});
