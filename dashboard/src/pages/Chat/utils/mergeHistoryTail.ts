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
export function inFlightTail(current: ChatMessage[]): ChatMessage[] {
  const idx = lastUserIndex(current);
  if (idx < 0) return current;
  return current.slice(idx);
}

function assistantRichness(messages: ChatMessage[]): number {
  let score = 0;
  for (const message of messages) {
    if (message.role !== "assistant" || message.toolData) continue;
    score += (message.content || "").length;
    for (const block of message.contentBlocks ?? []) {
      if (block.type === "text") score += (block.content || "").length;
    }
    if (message.status === "streaming") score += 1;
  }
  return score;
}

function toolRichness(messages: ChatMessage[]): number {
  let score = 0;
  for (const message of messages) {
    if (message.role !== "tool" && !message.toolData) continue;
    score += 1;
    score += (message.content || "").length;
    score += (message.toolData?.output || "").length;
    score += (message.toolData?.arguments || "").length;
  }
  return score;
}

/** Assistant text decides. Tool bulk is only a tie-break so a long tool result cannot hide a newer reply. */
function localTailRicher(local: ChatMessage[], server: ChatMessage[]): boolean {
  const localAssistant = assistantRichness(local);
  const serverAssistant = assistantRichness(server);
  if (localAssistant !== serverAssistant)
    return localAssistant > serverAssistant;
  return toolRichness(local) > toolRichness(server);
}

/**
 * Same user text, and the local copy is not a later resend of that text.
 * Returns the user indexes, or null when the tails are different turns.
 */
function sameUserTurn(
  base: ChatMessage[],
  tail: ChatMessage[],
): { baseUserIdx: number; tailUserIdx: number } | null {
  const tailUserIdx = lastUserIndex(tail);
  if (tailUserIdx < 0) return null;
  const tailText = textOf(tail[tailUserIdx]);
  if (!tailText) return null;
  const baseUserIdx = lastUserIndex(base);
  if (baseUserIdx < 0) return null;
  if (textOf(base[baseUserIdx]) !== tailText) return null;
  const baseTs = base[baseUserIdx].timestamp || 0;
  const tailTs = tail[tailUserIdx].timestamp || 0;
  if (baseTs > 0 && tailTs > baseTs + 1000) return null;
  return { baseUserIdx, tailUserIdx };
}

/**
 * Keep a local reply when the server copy of the same turn is shorter.
 * A finished server turn with at least as much text wins, so ids stay stable.
 */
function applyRicherTail(
  base: ChatMessage[],
  localTail: ChatMessage[],
): ChatMessage[] {
  if (localTail.length === 0) return base;
  const match = sameUserTurn(base, localTail);
  if (!match) return [...base, ...localTail];
  const baseAfter = base.slice(match.baseUserIdx + 1);
  const tailAfter = localTail.slice(match.tailUserIdx + 1);
  if (localTailRicher(tailAfter, baseAfter)) {
    return [...base.slice(0, match.baseUserIdx + 1), ...tailAfter];
  }
  return base;
}

/**
 * Fold a cached in-flight tail into messages already on screen.
 * A tail from a different turn is ignored so a stale cache cannot be appended.
 */
export function preferLocalTranscript(
  memory: ChatMessage[],
  cached: ChatMessage[] | null | undefined,
): ChatMessage[] {
  if (!cached || cached.length === 0) return memory;
  if (memory.length === 0) return cached;
  const tail = inFlightTail(cached);
  const match = sameUserTurn(memory, tail);
  if (!match) return memory;
  const baseAfter = memory.slice(match.baseUserIdx + 1);
  const tailAfter = tail.slice(match.tailUserIdx + 1);
  if (localTailRicher(tailAfter, baseAfter)) {
    return [...memory.slice(0, match.baseUserIdx + 1), ...tailAfter];
  }
  return memory;
}

/** True when `loaded` already contains everything the cache was holding. */
export function serverCaughtUp(
  loaded: ChatMessage[],
  cached: ChatMessage[],
): boolean {
  if (cached.length === 0) return true;
  return applyRicherTail(loaded, inFlightTail(cached)) === loaded;
}

/**
 * Apply a server history page without dropping a turn the user just sent.
 *
 * Opening an old thread fetches history before the optimistic bubble exists.
 * The response then replaces the list and the bubble vanishes, while the
 * WebSocket turn keeps running. Messages after the last shared id are that
 * local turn and stay on screen until the server page already includes them.
 *
 * An in-flight reply is not in the database until the turn finishes, so a
 * history page can contain the user message (or a shorter checkpoint) while
 * the browser still holds the longer stream. The longer assistant tail wins.
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
    return applyRicherTail(loaded, inFlightTail(current));
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
  if (localTailRicher(localTail, serverAfter)) {
    const head = base.slice(0, base.length - serverAfter.length);
    return [...head, ...localTail];
  }
  return base;
}
