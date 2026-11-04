import type { ChatMessage } from "../hooks/sseHelpers";
import { inFlightTail } from "./mergeHistoryTail";

const STORAGE_PREFIX = "octop:inflight-transcript:";
const MAX_TEXT = 80_000;
const MAX_CACHE_CHARS = 1_500_000;
const WRITE_DELAY_MS = 200;

const writeTimers = new Map<string, ReturnType<typeof setTimeout>>();
const latestByThread = new Map<string, ChatMessage[]>();
const recoveryByThread = new Map<string, ChatMessage[]>();

function storageKey(threadId: string): string {
  return `${STORAGE_PREFIX}${threadId}`;
}

function clipText(value: string | undefined): string {
  if (!value) return "";
  if (value.length <= MAX_TEXT) return value;
  return value.slice(0, MAX_TEXT);
}

function slimMessage(message: ChatMessage): ChatMessage {
  return {
    id: message.id,
    role: message.role,
    content:
      message.role === "user" ? message.content : clipText(message.content),
    attachments: message.attachments,
    composerContext: message.composerContext,
    hitlData: message.hitlData,
    delivery: message.delivery,
    turnId: message.turnId,
    serverOrder: message.serverOrder,
    historyTurnId: message.historyTurnId,
    turnStatus: message.turnStatus,
    contentBlocks: message.contentBlocks?.map((block) => ({
      type: block.type,
      content: clipText(block.content),
    })),
    status: message.status,
    timestamp: message.timestamp || 0,
    durationMs:
      typeof message.durationMs === "number" && message.durationMs >= 0
        ? Math.round(message.durationMs)
        : undefined,
    speakerAgentId: message.speakerAgentId,
    teamWrapup: message.teamWrapup,
    errorInfo: message.errorInfo,
    toolData: message.toolData
      ? {
          name: message.toolData.name,
          displayName: message.toolData.displayName,
          callId: message.toolData.callId,
          arguments: clipText(message.toolData.arguments),
          output: clipText(message.toolData.output),
        }
      : undefined,
  };
}

function isRole(value: unknown): value is ChatMessage["role"] {
  return (
    value === "user" ||
    value === "assistant" ||
    value === "system" ||
    value === "tool"
  );
}

function parseTail(
  raw: string,
  field: "tail" | "recovery" = "tail",
): ChatMessage[] | null {
  try {
    const parsed = JSON.parse(raw) as {
      v?: unknown;
      tail?: unknown;
      recovery?: unknown;
    };
    const messages = parsed[field];
    if ((parsed.v !== 1 && parsed.v !== 2) || !Array.isArray(messages))
      return null;
    const tail: ChatMessage[] = [];
    for (const item of messages) {
      if (!item || typeof item !== "object") return null;
      const row = item as Partial<ChatMessage>;
      if (typeof row.id !== "string" || !isRole(row.role)) return null;
      tail.push({
        id: row.id,
        role: row.role,
        content: typeof row.content === "string" ? row.content : "",
        attachments: Array.isArray(row.attachments)
          ? row.attachments
          : undefined,
        composerContext: row.composerContext,
        hitlData: row.hitlData,
        delivery:
          row.delivery === "pending" || row.delivery === "accepted"
            ? row.delivery
            : undefined,
        turnId: typeof row.turnId === "string" ? row.turnId : undefined,
        serverOrder:
          Array.isArray(row.serverOrder) &&
          row.serverOrder.length === 2 &&
          row.serverOrder.every(Number.isSafeInteger)
            ? row.serverOrder
            : undefined,
        historyTurnId:
          typeof row.historyTurnId === "string" ? row.historyTurnId : undefined,
        turnStatus:
          typeof row.turnStatus === "string" ? row.turnStatus : undefined,
        contentBlocks: Array.isArray(row.contentBlocks)
          ? row.contentBlocks.flatMap((block) => {
              if (!block || typeof block !== "object") return [];
              const typed = block as { type?: unknown; content?: unknown };
              if (typed.type !== "text" && typed.type !== "thinking") return [];
              return [
                {
                  type: typed.type,
                  content:
                    typeof typed.content === "string" ? typed.content : "",
                },
              ];
            })
          : undefined,
        status:
          row.status === "streaming" ||
          row.status === "done" ||
          row.status === "error"
            ? row.status
            : undefined,
        timestamp: typeof row.timestamp === "number" ? row.timestamp : 0,
        durationMs:
          typeof row.durationMs === "number" && row.durationMs >= 0
            ? Math.round(row.durationMs)
            : undefined,
        speakerAgentId:
          typeof row.speakerAgentId === "string"
            ? row.speakerAgentId
            : undefined,
        teamWrapup: row.teamWrapup === true ? true : undefined,
        toolData:
          row.toolData && typeof row.toolData === "object"
            ? row.toolData
            : undefined,
        errorInfo:
          row.errorInfo && typeof row.errorInfo === "object"
            ? row.errorInfo
            : undefined,
      });
    }
    return tail;
  } catch {
    return null;
  }
}

function encodeTail(
  messages: ChatMessage[],
): { v: number; tail: ChatMessage[] } | null | undefined {
  const tail = inFlightTail(messages).map(slimMessage);
  if (tail.length === 0) return null;
  if (JSON.stringify(tail).length <= MAX_CACHE_CHARS) return { v: 2, tail };
  const lighter = tail.map((message) =>
    message.toolData
      ? {
          ...message,
          toolData: {
            ...message.toolData,
            arguments: undefined,
            output: undefined,
          },
        }
      : message,
  );
  if (JSON.stringify(lighter).length <= MAX_CACHE_CHARS)
    return { v: 2, tail: lighter };
  return undefined;
}

function writeNow(threadId: string, messages: ChatMessage[]): boolean {
  try {
    const recovery = readRecoveryMessages(threadId);
    const recoveryIds = new Set(recovery.map((m) => m.id));
    const active = messages.filter((m) => !recoveryIds.has(m.id));
    const payload = encodeTail(active);
    if (payload === undefined) return false;
    const key = storageKey(threadId);
    if (!payload && !recovery.length) sessionStorage.removeItem(key);
    else
      sessionStorage.setItem(
        key,
        JSON.stringify({
          v: 2,
          tail: payload?.tail ?? [],
          recovery: recovery.map(slimMessage),
        }),
      );
    return true;
  } catch {
    // One atomic envelope retains both active sends and uncertain recovery.
    // A failed update must leave the previous successful envelope untouched.
    return false;
  }
}

/** Read the in-flight turn cached for this thread, if any. */
export function readInflightTail(threadId: string): ChatMessage[] | null {
  if (!threadId || threadId.startsWith("__")) return null;
  const queued = latestByThread.get(threadId);
  if (queued) return inFlightTail(queued);
  try {
    const raw = sessionStorage.getItem(storageKey(threadId));
    if (!raw) return null;
    const tail = parseTail(raw);
    return tail?.length ? tail : null;
  } catch {
    return null;
  }
}

/** Recovery and active sends share an atomic storage envelope, but separate state. */
export function readRecoveryMessages(threadId: string): ChatMessage[] {
  const memory = recoveryByThread.get(threadId);
  if (memory) return memory;
  try {
    return (
      parseTail(
        sessionStorage.getItem(storageKey(threadId)) || "",
        "recovery",
      ) ?? []
    );
  } catch {
    return [];
  }
}

export function saveRecoveryMessages(
  threadId: string,
  messages: ChatMessage[],
): void {
  const active = readInflightTail(threadId) ?? [];
  // Remember even a failed storage update so a later send cannot overwrite it.
  recoveryByThread.set(threadId, messages);
  writeNow(threadId, active);
}

export function hasInflightTail(threadId: string): boolean {
  if (writeTimers.has(threadId)) return true;
  return readInflightTail(threadId) != null;
}

/**
 * Persist the current turn at most once per window.
 * A trailing debounce never fires while tokens arrive continuously.
 */
export function scheduleInflightTail(
  threadId: string,
  messages: ChatMessage[],
): void {
  if (!threadId || threadId.startsWith("__")) return;
  latestByThread.set(threadId, messages);
  if (writeTimers.has(threadId)) return;
  writeTimers.set(
    threadId,
    setTimeout(() => {
      writeTimers.delete(threadId);
      const tail = latestByThread.get(threadId);
      latestByThread.delete(threadId);
      if (tail) writeNow(threadId, tail);
    }, WRITE_DELAY_MS),
  );
}

/** Write immediately (stream end, or tests). */
export function flushInflightTail(
  threadId: string,
  messages: ChatMessage[],
): void {
  if (!threadId || threadId.startsWith("__")) return;
  const pending = writeTimers.get(threadId);
  if (pending !== undefined) {
    clearTimeout(pending);
    writeTimers.delete(threadId);
  }
  latestByThread.delete(threadId);
  writeNow(threadId, messages);
}

export function clearInflightTail(threadId: string): void {
  const pending = writeTimers.get(threadId);
  if (pending !== undefined) {
    clearTimeout(pending);
    writeTimers.delete(threadId);
  }
  latestByThread.delete(threadId);
  writeNow(threadId, []);
}

export function moveInflightTail(fromId: string, toId: string): void {
  if (!fromId || !toId || fromId === toId || toId.startsWith("__")) return;
  const active = readInflightTail(fromId) ?? [];
  const recovery = [
    ...new Map(
      [...readRecoveryMessages(toId), ...readRecoveryMessages(fromId)].map(
        (m) => [m.id, m],
      ),
    ).values(),
  ];
  recoveryByThread.set(toId, recovery);
  if (!writeNow(toId, active)) return;
  const pending = writeTimers.get(fromId);
  if (pending !== undefined) clearTimeout(pending);
  writeTimers.delete(fromId);
  latestByThread.delete(fromId);
  recoveryByThread.delete(fromId);
  try {
    sessionStorage.removeItem(storageKey(fromId));
  } catch {
    /* Keep the destination copy. */
  }
}
