import type { ChatMessage } from "../hooks/sseHelpers";

function lastUserIndex(messages: ChatMessage[]): number {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "user") return i;
  }
  return -1;
}

/** Local turn still on screen: from the latest user message through the end. */
export function inFlightTail(current: ChatMessage[]): ChatMessage[] {
  const pending = current.findIndex(
    (message) => message.role === "user" && message.localPending,
  );
  if (pending >= 0) return current.slice(pending);
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
  if (memory.length === 0) return memory;
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
  const loadedIds = new Set(loaded.map((message) => message.id));
  if (
    cached.some(
      (message) => message.role === "user" && !loadedIds.has(message.id),
    )
  )
    return false;
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
    (message) =>
      message.role === "user" &&
      message.localPending &&
      !loadedIds.has(message.id),
  );
}

/** Keep a paging boundary only when a persisted prefix overlaps this page. */
export function retainedHistoryPrefix(
  loaded: ChatMessage[],
  current: ChatMessage[],
): ChatMessage[] {
  const ids = new Set(loaded.map((message) => message.id));
  const overlap = current.findIndex((message) => ids.has(message.id));
  if (overlap <= 0 || current[overlap].localPending) return [];
  const prefix = current.slice(0, overlap);
  return prefix.every(
    (message) => !message.localPending && message.status !== "streaming",
  )
    ? prefix
    : [];
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

  const loadedIds = new Set(loaded.map((message) => message.id));
  const firstOverlap = current.findIndex((message) =>
    loadedIds.has(message.id),
  );

  if (firstOverlap < 0) {
    // Missing from the latest page does not mean newer: it may be old cache
    // outside the page. Only a send created in this running store can append.
    const pending = newSendIndex(current, loadedIds);
    if (pending < 0) return loaded;
    return appendPendingTurn(loaded, current.slice(pending));
  }

  let lastOverlap = firstOverlap;
  for (let i = current.length - 1; i >= 0; i--) {
    if (loadedIds.has(current[i].id)) {
      lastOverlap = i;
      break;
    }
  }

  const olderPrefix = retainedHistoryPrefix(loaded, current);
  const localTail = current.slice(lastOverlap + 1);
  const base = [...olderPrefix, ...loaded];
  if (localTail.length === 0) return base;

  const freshSend = newSendIndex(localTail, loadedIds);
  if (freshSend >= 0) {
    // The latest page can already contain this turn's answer while the
    // optimistic question is still local. Only rows newer than that question
    // move behind it. An older row the client has not seen yet stays put.
    const question = localTail[freshSend];
    const questionTs = question?.timestamp ?? 0;
    const priorIds = new Set(
      current
        .slice(0, lastOverlap + 1 + freshSend)
        .map((message) => message.id),
    );
    const beforeSend: ChatMessage[] = [];
    const afterSend: ChatMessage[] = [];
    for (const message of base) {
      const ts = message.timestamp ?? 0;
      if (!priorIds.has(message.id) && questionTs > 0 && ts > questionTs) {
        afterSend.push(message);
      } else {
        beforeSend.push(message);
      }
    }
    return [...beforeSend, ...localTail.slice(freshSend), ...afterSend];
  }

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

/**
 * Place a not-yet-stored question after history, but keep a stored reply that
 * is newer than that question behind it. A long tool turn can fill the latest
 * page with the answer before the optimistic user id is in the page.
 */
function appendPendingTurn(
  before: ChatMessage[],
  pendingTurn: ChatMessage[],
): ChatMessage[] {
  const user = pendingTurn.find((message) => message.role === "user");
  const userTs = user?.timestamp ?? 0;
  if (!user || userTs <= 0) return [...before, ...pendingTurn];
  // A page that already has an older timestamp is real history: a row with
  // no timestamp stays with that history. A page with no older timestamp is
  // the tail of this turn, including when the stored answer has no timestamp.
  const hasOlderTimestamp = before.some((message) => {
    const ts = message.timestamp ?? 0;
    return ts > 0 && ts <= userTs;
  });
  const older: ChatMessage[] = [];
  const newer: ChatMessage[] = [];
  for (const message of before) {
    const ts = message.timestamp ?? 0;
    const afterQuestion = ts > userTs || (ts <= 0 && !hasOlderTimestamp);
    if (afterQuestion) newer.push(message);
    else older.push(message);
  }
  return [...older, ...pendingTurn, ...newer];
}
