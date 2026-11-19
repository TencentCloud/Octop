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

/**
 * Keep a turn the server has not stored yet.
 *
 * History is written when the request finishes. A refresh while that turn is
 * still running loads the previous page, and the cached user id is absent, so
 * the in-flight reply would otherwise disappear until the next refresh.
 * Only an active turn may bring that cache back; a finished unmatched tail
 * stays off the latest page.
 */
export function restoreUnpersistedTurn(
  folded: ChatMessage[],
  cached: ChatMessage[] | null | undefined,
  turnActive: boolean,
): ChatMessage[] {
  if (!turnActive || !cached || cached.length === 0) return folded;
  const tail = inFlightTail(cached);
  const userIdx = lastUserIndex(tail);
  if (userIdx < 0) return folded;
  const user = tail[userIdx];
  if (folded.some((message) => message.id === user.id)) return folded;
  const reply = tail.slice(userIdx + 1);
  // A finished tail whose user row is not on this page is an older turn.
  // Only the turn still streaming (or a question with no reply yet) belongs
  // on the latest page.
  const stillRunning =
    reply.length === 0 ||
    reply.some((message) => message.status === "streaming");
  if (!stillRunning) return folded;
  const pending = tail.slice(userIdx).map((message) => {
    const row =
      message.role === "assistant" &&
      message.status === "streaming" &&
      !message.turnId
        ? { ...message, status: "done" as const }
        : message;
    return row.id === user.id ? { ...row, localPending: true } : row;
  });
  return [...folded, ...pending];
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

/** Keep chips the live bubble already showed when the stored row omitted them. */
export function preserveLocalComposerContext(
  loaded: ChatMessage[],
  local: ChatMessage[],
): ChatMessage[] {
  const byId = new Map<string, ChatMessage["composerContext"]>();
  for (const message of local) {
    if (message.role === "user" && message.composerContext) {
      byId.set(message.id, message.composerContext);
    }
  }
  if (byId.size === 0) return loaded;
  return loaded.map((message) => {
    if (message.role !== "user") return message;
    const previous = byId.get(message.id);
    if (!previous) return message;
    const server = message.composerContext;
    if (!server) return { ...message, composerContext: previous };
    return {
      ...message,
      composerContext: {
        skills: server.skills?.length ? server.skills : previous.skills,
        connectors: server.connectors?.length
          ? server.connectors
          : previous.connectors,
        knowledgeBaseIds: server.knowledgeBaseIds?.length
          ? server.knowledgeBaseIds
          : previous.knowledgeBaseIds,
        targetAgents: server.targetAgents?.length
          ? server.targetAgents
          : previous.targetAgents,
        model: server.model || previous.model,
        reasoningMode: server.reasoningMode || previous.reasoningMode,
        reasoningEffort: server.reasoningEffort || previous.reasoningEffort,
      },
    };
  });
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
  let lastOverlap = -1;
  for (let i = current.length - 1; i >= 0; i--) {
    if (loadedIds.has(current[i].id)) {
      lastOverlap = i;
      break;
    }
  }

  const olderPrefix = retainedHistoryPrefix(loaded, current);
  const base = [...olderPrefix, ...loaded];
  const storedQuestions = new Set(
    loaded.map((message) => message.turnUserMessageId),
  );
  const pending = current.findIndex(
    (message, index) =>
      message.role === "user" &&
      message.localPending &&
      !loadedIds.has(message.id) &&
      (index > lastOverlap || storedQuestions.has(message.id)),
  );
  if (pending >= 0) {
    return mergePendingTurns(base, current.slice(pending), loadedIds);
  }

  if (lastOverlap < 0) return loaded;
  const localTail = current.slice(lastOverlap + 1);
  if (localTail.length === 0) return base;

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

/** Insert a missing question before its stored replies, preserving server order. */
function mergePendingTurns(
  history: ChatMessage[],
  pending: ChatMessage[],
  loadedIds: Set<string>,
): ChatMessage[] {
  const result: ChatMessage[] = [];
  let historyStart = 0;
  let localStart = 0;
  let questionIndex = 0;
  for (let end = 1; end <= pending.length; end++) {
    if (end < pending.length && pending[end].role !== "user") continue;
    const question = pending[questionIndex];
    questionIndex = end;
    if (!question.localPending || loadedIds.has(question.id)) continue;
    const firstReply = history.findIndex(
      (message, index) =>
        index >= historyStart && message.turnUserMessageId === question.id,
    );
    if (firstReply < 0) continue;
    result.push(
      ...history.slice(historyStart, firstReply),
      ...pending
        .slice(localStart, end)
        .filter((message) => !loadedIds.has(message.id)),
    );
    historyStart = firstReply;
    localStart = end;
  }
  return [
    ...result,
    ...history.slice(historyStart),
    ...pending
      .slice(localStart)
      .filter((message) => !loadedIds.has(message.id)),
  ];
}
