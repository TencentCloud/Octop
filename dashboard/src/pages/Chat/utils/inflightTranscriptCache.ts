import type { ChatMessage } from "../hooks/sseHelpers";
import { inFlightTail } from "./mergeHistoryTail";

const STORAGE_PREFIX = "octop:inflight-transcript:";
const MAX_TEXT = 80_000;
const MAX_CACHE_CHARS = 1_500_000;
const WRITE_DELAY_MS = 200;

const writeTimers = new Map<string, ReturnType<typeof setTimeout>>();
const latestByThread = new Map<string, ChatMessage[]>();

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
    content: clipText(message.content),
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

function parseTail(raw: string): ChatMessage[] | null {
  try {
    const parsed = JSON.parse(raw) as { v?: unknown; tail?: unknown };
    if (parsed.v !== 1 || !Array.isArray(parsed.tail)) return null;
    const tail: ChatMessage[] = [];
    for (const item of parsed.tail) {
      if (!item || typeof item !== "object") return null;
      const row = item as Partial<ChatMessage>;
      if (typeof row.id !== "string" || !isRole(row.role)) return null;
      tail.push({
        id: row.id,
        role: row.role,
        content: typeof row.content === "string" ? row.content : "",
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

function encodeTail(messages: ChatMessage[]): string | null {
  const tail = inFlightTail(messages).map(slimMessage);
  if (tail.length === 0) return null;
  let raw = JSON.stringify({ v: 1, tail });
  if (raw.length <= MAX_CACHE_CHARS) return raw;
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
  raw = JSON.stringify({ v: 1, tail: lighter });
  if (raw.length <= MAX_CACHE_CHARS) return raw;
  return null;
}

function writeNow(threadId: string, messages: ChatMessage[]): void {
  const key = storageKey(threadId);
  try {
    const raw = encodeTail(messages);
    if (!raw) {
      sessionStorage.removeItem(key);
      return;
    }
    sessionStorage.setItem(key, raw);
  } catch {
    try {
      sessionStorage.removeItem(key);
    } catch {
      // sessionStorage unavailable or quota exceeded
    }
  }
}

/** Read the in-flight turn cached for this thread, if any. */
export function readInflightTail(threadId: string): ChatMessage[] | null {
  if (!threadId || threadId.startsWith("__")) return null;
  try {
    const raw = sessionStorage.getItem(storageKey(threadId));
    if (!raw) return null;
    return parseTail(raw);
  } catch {
    return null;
  }
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
  try {
    sessionStorage.removeItem(storageKey(threadId));
  } catch {
    // ignore
  }
}

export function moveInflightTail(fromId: string, toId: string): void {
  if (!fromId || !toId || fromId === toId) return;
  const pending = writeTimers.get(fromId);
  if (pending !== undefined) {
    clearTimeout(pending);
    writeTimers.delete(fromId);
  }
  const latest = latestByThread.get(fromId);
  latestByThread.delete(fromId);
  if (latest && !toId.startsWith("__")) {
    writeNow(toId, latest);
    try {
      sessionStorage.removeItem(storageKey(fromId));
    } catch {
      // ignore
    }
    return;
  }
  try {
    const raw = sessionStorage.getItem(storageKey(fromId));
    if (raw && !toId.startsWith("__")) {
      sessionStorage.setItem(storageKey(toId), raw);
    }
    sessionStorage.removeItem(storageKey(fromId));
  } catch {
    // ignore
  }
}
