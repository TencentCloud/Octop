import { describe, expect, it } from "vitest";
import { nextCanLoadOlder, shouldReleaseLoadMoreLatch } from "./loadOlderGate";

describe("nextCanLoadOlder", () => {
  it("disarms on session reset", () => {
    expect(
      nextCanLoadOlder({
        kind: "session-reset",
        loading: false,
        messageCount: 40,
      }),
    ).toBe(false);
  });

  it("re-arms after session reset when cached history is ready", () => {
    expect(
      nextCanLoadOlder({
        kind: "session-reset",
        loading: false,
        messageCount: 40,
      }),
    ).toBe(false);
    expect(
      nextCanLoadOlder({
        kind: "history-ready",
        loading: false,
        messageCount: 40,
      }),
    ).toBe(true);
  });

  it("stays disarmed while initial history is loading", () => {
    expect(
      nextCanLoadOlder({
        kind: "history-ready",
        loading: true,
        messageCount: 0,
      }),
    ).toBe(false);
  });

  it("arms after initial history finishes", () => {
    expect(
      nextCanLoadOlder({
        kind: "history-ready",
        loading: false,
        messageCount: 25,
      }),
    ).toBe(true);
  });
});

describe("shouldReleaseLoadMoreLatch", () => {
  it("releases when loadMoreHistory declines to start", () => {
    expect(shouldReleaseLoadMoreLatch(false)).toBe(true);
  });

  it("keeps latch when load started (cleared later by historyLoadingMore)", () => {
    expect(shouldReleaseLoadMoreLatch(true)).toBe(false);
  });

  it("keeps latch for void/undefined return (legacy callers)", () => {
    expect(shouldReleaseLoadMoreLatch(undefined)).toBe(false);
    expect(shouldReleaseLoadMoreLatch()).toBe(false);
  });
});
