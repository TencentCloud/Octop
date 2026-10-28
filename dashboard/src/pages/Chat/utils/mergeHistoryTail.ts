import type { ChatMessage } from "../hooks/sseHelpers";

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

/** Match local and cached turns by the persisted user message id. */
function sameUserTurn(
  base: ChatMessage[],
  tail: ChatMessage[],
): { baseUserIdx: number; tailUserIdx: number } | null {
  const baseUserIdx = lastUserIndex(base);
  const tailUserIdx = lastUserIndex(tail);
  if (baseUserIdx < 0 || tailUserIdx < 0) return null;
  if (base[baseUserIdx].id !== tail[tailUserIdx].id) return null;
  return { baseUserIdx, tailUserIdx };
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

/** True when server history can replace this cached turn. */
export function serverCaughtUp(
  loaded: ChatMessage[],
  cached: ChatMessage[],
): boolean {
  if (cached.length === 0) return true;
  const tail = inFlightTail(cached);
  const userIdx = lastUserIndex(tail);
  if (userIdx < 0) return false;
  const loadedUserIdx = loaded.findIndex(
    (message) => message.role === "user" && message.id === tail[userIdx].id,
  );
  if (loadedUserIdx < 0) return false;
  const localReply = tail.slice(userIdx + 1);
  if (localReply.length === 0) return true;
  const serverReply = loaded.slice(loadedUserIdx + 1);
  if (serverReply.length === 0) return false;
  // A later stored user turn also retires an older cached stream.
  if (serverReply.some((message) => message.role === "user")) return true;
  return (
    !localReply.some((message) => message.status === "streaming") ||
    !localTailRicher(localReply, serverReply)
  );
}

/** Index of a user message in `tail` whose id the server page does not have. */
function newSendIndex(tail: ChatMessage[], loadedIds: Set<string>): number {
  return tail.findIndex(
    (message) => message.role === "user" && !loadedIds.has(message.id),
  );
}

/**
 * Apply a server history page without dropping a turn the user just sent.
 *
 * The dashboard send stores the optimistic user id on the checkpoint
 * HumanMessage. A finished turn therefore shares that id with the server
 * page. Keep a richer local reply while streaming; after it finishes,
 * the server reply replaces the local bubbles, even if its text is shorter.
 * A later send keeps its own id until that row is stored.
 *
 * Opening an old thread fetches history before the optimistic bubble exists.
 * The response then replaces the list and the bubble vanishes, while the
 * WebSocket turn keeps running. Messages after the last shared id are that
 * local turn and stay on screen until the server page already includes them.
 */
export function mergeHistoryWithLocalTail(
  loaded: ChatMessage[],
  current: ChatMessage[],
  isStreaming = false,
): ChatMessage[] {
  if (current.length === 0) return loaded;
  if (loaded.length === 0) return current;

  const loadedIds = new Set(loaded.map((message) => message.id));
  const firstOverlap = current.findIndex((message) =>
    loadedIds.has(message.id),
  );

  if (firstOverlap < 0) {
    // This page does not contain the optimistic user id, so the turn is not
    // stored here yet.
    return [...loaded, ...inFlightTail(current)];
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

  const freshSend = newSendIndex(localTail, loadedIds);
  if (freshSend >= 0) return [...base, ...localTail.slice(freshSend)];

  const overlapId = current[lastOverlap].id;
  const loadedOverlap = loaded.findIndex((message) => message.id === overlapId);
  const serverAfter = loadedOverlap >= 0 ? loaded.slice(loadedOverlap + 1) : [];
  // User row is stored and the reply is not in this page yet.
  if (serverAfter.length === 0) return [...base, ...localTail];
  const live =
    isStreaming || localTail.some((message) => message.status === "streaming");
  if (
    live &&
    !serverAfter.some((message) => message.role === "user") &&
    localTailRicher(localTail, serverAfter)
  ) {
    return [...base.slice(0, base.length - serverAfter.length), ...localTail];
  }
  return base;
}
