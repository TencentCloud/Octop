/** Sidebar thread work status. Idle (done) is the default and has no badge. */
export type SessionWorkStatus = "working" | "waiting" | "idle";

export function resolveSessionWorkStatus(
  session: { id: string; turnActive?: boolean; awaitingUser?: boolean },
  liveWorkingIds: ReadonlySet<string>,
): SessionWorkStatus {
  if (liveWorkingIds.has(session.id) || session.turnActive) return "working";
  if (session.awaitingUser) return "waiting";
  return "idle";
}
