import { octopThreadsApi } from "../../../api/modules/octopThreads";
import { sortSessions, toSession, type Session } from "../hooks/useSessions";

/** First unread row in list order. Callers that sort with ``sortSessions`` put pinned threads first. */
export function pickUnreadSession(
  sessions: readonly Session[],
): Session | null {
  return sessions.find((session) => (session.unreadCount ?? 0) > 0) ?? null;
}

/** Open the first unread thread in list order, fetching the list if needed. */
export async function openAgentUnread(
  agentId: string,
  sessions: readonly Session[],
  onSelect: (sessionId: string, agentId: string) => void,
): Promise<void> {
  const local = pickUnreadSession(sessions);
  if (local) {
    onSelect(local.id, agentId);
    return;
  }
  try {
    const rows = await octopThreadsApi.list(agentId, 50);
    const fetched = pickUnreadSession(sortSessions(rows.map(toSession)));
    if (fetched) onSelect(fetched.id, agentId);
  } catch {
    // Leave the current selection when the thread list cannot be loaded.
  }
}
