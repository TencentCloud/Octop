import { describe, expect, it } from "vitest";
import { sortSessions, type Session } from "../hooks/useSessions";
import { pickUnreadSession } from "./openUnreadSession";

function session(
  partial: Pick<Session, "id"> &
    Partial<Pick<Session, "unreadCount" | "pinned" | "updatedAt">>,
): Session {
  return {
    name: partial.id,
    threadId: partial.id,
    channelType: "dashboard",
    updatedAt: null,
    ...partial,
  };
}

describe("pickUnreadSession", () => {
  it("follows list order, so a pinned unread comes before a newer one", () => {
    const sessions = sortSessions([
      session({
        id: "new",
        unreadCount: 2,
        pinned: false,
        updatedAt: "2026-11-06T12:00:00.000Z",
      }),
      session({
        id: "pinned",
        unreadCount: 1,
        pinned: true,
        updatedAt: "2026-11-01T12:00:00.000Z",
      }),
      session({ id: "read", unreadCount: 0, pinned: false }),
    ]);

    expect(pickUnreadSession(sessions)?.id).toBe("pinned");
  });

  it("returns null when nothing is unread", () => {
    expect(pickUnreadSession([session({ id: "read", unreadCount: 0 })])).toBe(
      null,
    );
  });
});
