import type { ChatMessage } from "../hooks/sseHelpers";

function textOf(message: ChatMessage): string {
  return (message.content || "").trim();
}

function lastUserIndex(messages: ChatMessage[]): number {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "user") return i;
  }
  return -1;
}

/** Local turn still on screen: from the latest user message through the end. */
function inFlightTail(current: ChatMessage[]): ChatMessage[] {
  const idx = lastUserIndex(current);
  if (idx < 0) return current;
  return current.slice(idx);
}

/**
 * True when `base` already ends with this local turn (server persisted it
 * under different ids). A later send of the same text is kept.
 */
function sameTurnAlreadyLoaded(
  base: ChatMessage[],
  tail: ChatMessage[],
): boolean {
  const tailUserIdx = lastUserIndex(tail);
  if (tailUserIdx < 0) return false;
  const tailUser = tail[tailUserIdx];
  const tailText = textOf(tailUser);
  if (!tailText) return false;
  const baseUserIdx = lastUserIndex(base);
  if (baseUserIdx < 0) return false;
  const baseUser = base[baseUserIdx];
  if (textOf(baseUser) !== tailText) return false;
  const baseTs = baseUser.timestamp || 0;
  const tailTs = tailUser.timestamp || 0;
  if (baseTs > 0 && tailTs > baseTs + 1000) return false;
  return true;
}

/**
 * Apply a server history page without dropping a turn the user just sent.
 *
 * Opening an old thread fetches history before the optimistic bubble exists.
 * The response then replaces the list and the bubble vanishes, while the
 * WebSocket turn keeps running. Messages after the last shared id are that
 * local turn and stay on screen until the server page already includes them.
 */
export function mergeHistoryWithLocalTail(
  loaded: ChatMessage[],
  current: ChatMessage[],
): ChatMessage[] {
  if (current.length === 0) return loaded;
  if (loaded.length === 0) return current;

  const loadedIds = new Set(loaded.map((message) => message.id));
  const firstOverlap = current.findIndex((message) =>
    loadedIds.has(message.id),
  );

  if (firstOverlap < 0) {
    const tail = inFlightTail(current);
    if (sameTurnAlreadyLoaded(loaded, tail)) return loaded;
    return [...loaded, ...tail];
  }

  let lastOverlap = firstOverlap;
  for (let i = current.length - 1; i >= 0; i--) {
    if (loadedIds.has(current[i].id)) {
      lastOverlap = i;
      break;
    }
  }

  const olderPrefix = current.slice(0, firstOverlap);
  const localTail = current.slice(lastOverlap + 1);
  const base = [...olderPrefix, ...loaded];
  if (localTail.length === 0) return base;

  const overlapId = current[lastOverlap].id;
  const loadedOverlap = loaded.findIndex((message) => message.id === overlapId);
  const serverAfter = loadedOverlap >= 0 ? loaded.slice(loadedOverlap + 1) : [];
  if (serverAfter.length === 0) return [...base, ...localTail];
  if (sameTurnAlreadyLoaded(serverAfter, localTail)) return base;
  return [...base, ...localTail];
}
