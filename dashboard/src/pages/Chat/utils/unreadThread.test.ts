import { describe, expect, it } from "vitest";
import { firstUnreadThreadId } from "./unreadThread";

describe("firstUnreadThreadId", () => {
  it("returns the first unread thread from the server-ordered list", () => {
    expect(
      firstUnreadThreadId([
        { thread_id: "newest-read", unread_count: 0 },
        { thread_id: "newest-unread", unread_count: 2 },
        { thread_id: "older-unread", unread_count: 1 },
      ]),
    ).toBe("newest-unread");
  });

  it("ignores missing counts and returns null when nothing is unread", () => {
    expect(
      firstUnreadThreadId([
        { thread_id: "missing-count" },
        { thread_id: "read", unread_count: 0 },
      ]),
    ).toBeNull();
  });
});
