/**
 * Module-level chat store that survives React component unmount/remount cycles.
 *
 * Key idea: WebSocket streams and accumulated messages live *outside* React.
 * Components subscribe to updates and get the latest snapshot on mount.
 * When the user navigates away and comes back, the messages (including
 * any in-flight streaming content) are still available.
 */

import { getApiUrl } from "../../../api/config";
import { getAuthToken } from "../../../api/request";
import { buildDashboardChatWsUrl } from "../../../api/modules/wsChat";
import { generateId } from "../../../utils/messageParser";
import type {
  ChatAttachment,
  ChatMessage,
  SessionSnapshot,
  SessionStreamState,
} from "./sseHelpers";
import {
  parseHarnessChunk,
  type HarnessChunk,
  type ToolCallChunk,
} from "../../../utils/parseHarnessChunk";
import { isChatStreamError } from "../../../utils/chatStreamError";
import { buildUserMessageContent } from "../utils/chatAttachments";
import { sealPriorStreamingAssistants as sealPriorStreamingAssistantsMessages } from "./sealPriorStreamingAssistants";
import { turnStatusAction } from "./turnStatusGate";
import {
  MAX_STREAM_RESUME_ATTEMPTS,
  STREAM_STALE_WITHOUT_SOCKET_MS,
  shouldEmitStreamResumeNotice,
  shouldForceSealStream,
  shouldResumeStreamAfterClose,
} from "./wsResumeGate";

// ── Focused chat session (reconnect thrash only for the visible tab) ──────

let focusedChatSessionId: string | null = null;

/** Tell the store which chat thread the UI is currently showing. */
export function setFocusedChatSession(sessionId: string | null): void {
  const next = sessionId && sessionId !== "__empty__" ? sessionId : null;
  const prev = focusedChatSessionId;
  focusedChatSessionId = next;
  if (next && next !== prev) {
    void rebindFocusedSessionIfNeeded(next);
  }
}

export function getFocusedChatSession(): string | null {
  return focusedChatSessionId;
}

function isSessionFocused(sessionId: string): boolean {
  // Unset focus (unit tests / before first paint) → treat as focused.
  if (focusedChatSessionId == null) return true;
  return focusedChatSessionId === sessionId;
}

async function rebindFocusedSessionIfNeeded(sessionId: string): Promise<void> {
  const state = sessionStates.get(sessionId);
  if (!state?.isStreaming) return;
  if (isLiveSocketOpen(sessionId)) return;
  const liveMeta = pendingResumeBySession.get(sessionId);
  if (liveMeta) {
    pendingResumeBySession.delete(sessionId);
    void attachThread(
      sessionId,
      liveMeta.agentId,
      liveMeta.threadId,
      liveMeta.onStreamEnd,
      liveMeta.resumeAttempt,
      liveMeta.opts,
    );
    return;
  }
  // isStreaming sticky without pending meta — caller may still attach via loadHistory
}

/** Sessions that dropped while unfocused; re-attach when the tab is shown again. */
const pendingResumeBySession = new Map<
  string,
  {
    agentId: string;
    threadId: string;
    onStreamEnd?: () => void;
    resumeAttempt: number;
    opts?: { afterUnexpectedDrop?: boolean };
  }
>();

/** Try to open the dashboard chat WebSocket; null if construction fails. */
function tryOpenDashboardWs(agentId: string): WebSocket | null {
  try {
    return new WebSocket(buildDashboardChatWsUrl(agentId));
  } catch {
    return null;
  }
}

function sealInFlightAssistantMessages(state: SessionStreamState): void {
  state.messages = state.messages.map((m) =>
    m.status === "streaming" ? { ...m, status: "done" as const } : m,
  );
}

// ── Pending prefill text ──────────────────────────────────────────────────
// Set by external pages (e.g. cron-jobs suggestions) before navigating to
// /chat so the Chat input can be pre-populated reliably without relying on
// React Router location.state, which can be unreliable across mounts.
let _pendingPrefillText = "";

/** Enqueue a text to be pre-filled into the chat input on the next Chat mount. */
export function setPendingPrefillText(text: string): void {
  _pendingPrefillText = text;
}

/** Consume the pending prefill text (clears it after reading). */
export function consumePendingPrefillText(): string {
  const val = _pendingPrefillText;
  _pendingPrefillText = "";
  return val;
}

// ── Composer draft (sessionStorage) ───────────────────────────────────────
// Survives navigating away from /chat and back; keyed per agent + thread.

const DRAFT_STORAGE_PREFIX = "octop:chat-draft:";

function draftStorageKey(
  agentId: string,
  threadId: string | null | undefined,
): string {
  return `${DRAFT_STORAGE_PREFIX}${agentId}:${threadId ?? "__new__"}`;
}

/** Read a saved composer draft for *(agentId, threadId)*. */
export function readInputDraft(
  agentId: string | null | undefined,
  threadId: string | null | undefined,
): string {
  if (!agentId) return "";
  try {
    return sessionStorage.getItem(draftStorageKey(agentId, threadId)) ?? "";
  } catch {
    return "";
  }
}

/** Persist or clear the composer draft for *(agentId, threadId)*. */
export function writeInputDraft(
  agentId: string | null | undefined,
  threadId: string | null | undefined,
  text: string,
): void {
  if (!agentId) return;
  try {
    const key = draftStorageKey(agentId, threadId);
    if (text) sessionStorage.setItem(key, text);
    else sessionStorage.removeItem(key);
  } catch {
    // sessionStorage unavailable or quota exceeded
  }
}

// ── Re-export types so external consumers don't need changes ──────────────
export type {
  ChatAttachment,
  ChatMessage,
  HitlActionRequest,
  HitlRequestData,
  SessionSnapshot,
  SessionStreamState,
  ToolCallData,
  UserComposerContext,
} from "./sseHelpers";

/** Default snapshot for sessions that don't exist yet. Stable reference. */
const EMPTY_SNAPSHOT: SessionSnapshot = Object.freeze({
  messages: [],
  isStreaming: false,
  thinkingStartedAt: null,
  runUsage: null,
  contextUsage: null,
  historyHasMore: false,
  historyLoadingMore: false,
  historyNextOffset: 0,
  historyHydrated: false,
});

const sessionStates = new Map<string, SessionStreamState>();

// ── Tool / stream event hooks (for cross-module bridging) ──
export type ToolEventKind = "toolStart" | "toolDone";
export interface ToolEvent {
  kind: ToolEventKind;
  sessionId: string;
  toolName: string;
  toolId: string;
}
export type StreamEventKind = "streamStart" | "streamEnd" | "streamResume";
export interface StreamEvent {
  kind: StreamEventKind;
  sessionId: string;
}
export type SlashActionEvent = {
  action: string;
  agent_id?: string;
  sessionId?: string;
};
type ToolEventListener = (event: ToolEvent) => void;
type StreamEventListener = (event: StreamEvent) => void;
type SlashActionListener = (event: SlashActionEvent) => void;
const toolEventListeners = new Set<ToolEventListener>();
const streamEventListeners = new Set<StreamEventListener>();
const slashActionListeners = new Set<SlashActionListener>();

/** Register a listener for tool call start/done events. Returns unsubscribe fn. */
export function onToolEvent(listener: ToolEventListener): () => void {
  toolEventListeners.add(listener);
  return () => {
    toolEventListeners.delete(listener);
  };
}

/** Register a listener for stream start/end events. Returns unsubscribe fn. */
export function onStreamEvent(listener: StreamEventListener): () => void {
  streamEventListeners.add(listener);
  return () => {
    streamEventListeners.delete(listener);
  };
}

/** Register a listener for slash_action events (e.g. switch_agent). */
export function onSlashAction(listener: SlashActionListener): () => void {
  slashActionListeners.add(listener);
  return () => {
    slashActionListeners.delete(listener);
  };
}

export function emitToolEvent(event: ToolEvent) {
  for (const fn of toolEventListeners) {
    try {
      fn(event);
    } catch {
      /* ignore */
    }
  }
}

function emitStreamEvent(event: StreamEvent) {
  for (const fn of streamEventListeners) {
    try {
      fn(event);
    } catch {
      /* ignore */
    }
  }
}

function emitSlashAction(event: SlashActionEvent) {
  for (const fn of slashActionListeners) {
    try {
      fn(event);
    } catch {
      /* ignore */
    }
  }
}

// Session lifecycle events (e.g. deletion) for cross-module bridging.
export type SessionEventKind = "sessionDeleted";
export interface SessionEvent {
  kind: SessionEventKind;
  sessionId: string;
}
type SessionEventListener = (event: SessionEvent) => void;
const sessionEventListeners = new Set<SessionEventListener>();

/** Register a listener for session lifecycle events. Returns unsubscribe fn. */
export function onSessionEvent(listener: SessionEventListener): () => void {
  sessionEventListeners.add(listener);
  return () => {
    sessionEventListeners.delete(listener);
  };
}

export function emitSessionEvent(event: SessionEvent) {
  for (const fn of sessionEventListeners) {
    try {
      fn(event);
    } catch {
      /* ignore */
    }
  }
}

function buildSnapshot(state: SessionStreamState): SessionSnapshot {
  return {
    messages: state.messages,
    isStreaming: state.isStreaming,
    thinkingStartedAt: state.thinkingStartedAt,
    runUsage: state.runUsage,
    contextUsage: state.contextUsage,
    historyHasMore: state.historyHasMore,
    historyLoadingMore: state.historyLoadingMore,
    historyNextOffset: state.historyNextOffset,
    historyHydrated: state.historyHydrated,
  };
}

function getOrCreate(sessionId: string): SessionStreamState {
  let state = sessionStates.get(sessionId);
  if (!state) {
    state = {
      messages: [],
      isStreaming: false,
      thinkingStartedAt: null,
      runUsage: null,
      contextUsage: null,
      abortController: null,
      streamMsg: "",
      streamId: "",
      streamBlockType: "",
      toolCallIdIndex: {},
      historyHasMore: false,
      historyNextOffset: 0,
      historyLoadingMore: false,
      historyHydrated: false,
      listeners: new Set(),
      _snapshot: EMPTY_SNAPSHOT,
    };
    sessionStates.set(sessionId, state);
  }
  return state;
}

function notify(state: SessionStreamState) {
  // Rebuild the snapshot reference so useSyncExternalStore sees the change.
  state._snapshot = buildSnapshot(state);
  for (const fn of state.listeners) {
    try {
      fn();
    } catch {
      /* ignore */
    }
  }
}

function beginStream(state: SessionStreamState, sessionId: string): void {
  state.thinkingStartedAt = Date.now();
  state.isStreaming = true;
  touchStreamActivity(sessionId);
}

function clearStreamingFlags(state: SessionStreamState): void {
  state.isStreaming = false;
  state.thinkingStartedAt = null;
}

// ── Live WebSocket bookkeeping (used by cancel / attach / send) ────────────

type LiveSocket = {
  ws: WebSocket;
  agentId: string;
  threadId: string;
  /**
   * Socket was closed on purpose (replace / done / user stop). Unexpected drop
   * is false so auto-resume can re-subscribe.
   */
  intentionalClose: boolean;
  /**
   * User hit stop (or cancelStream). Distinct from intentional socket *replace*
   * while the server turn should keep running.
   */
  userCancelled: boolean;
};

const liveSockets = new Map<string, LiveSocket>();

/** Last stream-related activity (chunk / open / status) for sticky seals. */
const streamActivityAt = new Map<string, number>();
const streamWatchdogs = new Map<string, ReturnType<typeof setTimeout>>();

function isLiveSocketOpen(sessionId: string): boolean {
  const live = liveSockets.get(sessionId);
  if (!live) return false;
  return (
    live.ws.readyState === WebSocket.OPEN ||
    live.ws.readyState === WebSocket.CONNECTING
  );
}

/** True when this session currently owns an open/connecting chat WebSocket. */
export function hasLiveSocket(sessionId: string): boolean {
  return isLiveSocketOpen(sessionId);
}

function clearStreamWatchdog(sessionId: string): void {
  const timer = streamWatchdogs.get(sessionId);
  if (timer !== undefined) {
    clearTimeout(timer);
    streamWatchdogs.delete(sessionId);
  }
}

function touchStreamActivity(sessionId: string): void {
  streamActivityAt.set(sessionId, Date.now());
  armStreamWatchdog(sessionId);
}

function clearStreamActivity(sessionId: string): void {
  clearStreamWatchdog(sessionId);
  streamActivityAt.delete(sessionId);
}

/**
 * If isStreaming sticks without a live socket past the grace window, seal so
 * overscroll-refresh / free-scroll UX recover. Open sockets (long tools) skip.
 */
function armStreamWatchdog(sessionId: string): void {
  clearStreamWatchdog(sessionId);
  streamWatchdogs.set(
    sessionId,
    setTimeout(() => {
      streamWatchdogs.delete(sessionId);
      const state = sessionStates.get(sessionId);
      if (!state) return;
      if (
        !shouldForceSealStream({
          isStreaming: state.isStreaming,
          hasLiveSocket: isLiveSocketOpen(sessionId),
          lastActivityAt: streamActivityAt.get(sessionId) ?? null,
          now: Date.now(),
          staleWithoutSocketMs: STREAM_STALE_WITHOUT_SOCKET_MS,
          sessionFocused: isSessionFocused(sessionId),
        })
      ) {
        // Still streaming with a socket, within grace, or unfocused — re-check later.
        if (state.isStreaming && isSessionFocused(sessionId)) {
          armStreamWatchdog(sessionId);
        }
        return;
      }
      // Seal sticky stream without cancelling a server turn (no socket).
      clearStreamingFlags(state);
      state.streamMsg = "";
      state.streamId = "";
      state.streamBlockType = "";
      sealInFlightAssistantMessages(state);
      clearStreamActivity(sessionId);
      notify(state);
      emitStreamEvent({ kind: "streamEnd", sessionId });
    }, STREAM_STALE_WITHOUT_SOCKET_MS),
  );
}

// ── Public API ────────────────────────────────────────────────────────────

/** Subscribe to state changes for a session. Returns unsubscribe fn. */
export function subscribe(sessionId: string, listener: () => void): () => void {
  const state = getOrCreate(sessionId);
  state.listeners.add(listener);
  return () => {
    state.listeners.delete(listener);
  };
}

/** Get a read-only snapshot of the session state (referentially stable). */
export function getSnapshot(sessionId: string): SessionSnapshot {
  const state = sessionStates.get(sessionId);
  if (!state) return EMPTY_SNAPSHOT;
  return state._snapshot;
}

/** Directly set messages for a session (e.g. from loadHistory). */
export function setMessages(sessionId: string, messages: ChatMessage[]) {
  const state = getOrCreate(sessionId);
  state.messages = messages;
  state.runUsage = null;
  notify(state);
}

/** Replace messages and pagination cursor after an initial history load. */
export function setHistoryPage(
  sessionId: string,
  messages: ChatMessage[],
  opts: { hasMore: boolean; nextOffset: number },
) {
  const state = getOrCreate(sessionId);
  state.messages = messages;
  state.runUsage = null;
  state.historyHasMore = opts.hasMore;
  state.historyNextOffset = opts.nextOffset;
  state.historyLoadingMore = false;
  state.historyHydrated = true;
  notify(state);
}

function dedupePrependMessages(
  older: ChatMessage[],
  existing: ChatMessage[],
): ChatMessage[] {
  if (older.length === 0) return older;
  const seen = new Set(existing.map((message) => message.id));
  return older.filter((message) => !seen.has(message.id));
}

/** Prepend older messages when the user scrolls up. */
export function prependHistoryMessages(
  sessionId: string,
  older: ChatMessage[],
  opts: { hasMore: boolean; nextOffset: number },
) {
  const state = getOrCreate(sessionId);
  const uniqueOlder = dedupePrependMessages(older, state.messages);
  if (uniqueOlder.length > 0) {
    state.messages = [...uniqueOlder, ...state.messages];
  }
  state.historyHasMore = opts.hasMore;
  state.historyNextOffset = opts.nextOffset;
  notify(state);
}

export function setHistoryLoadingMore(sessionId: string, loading: boolean) {
  const state = getOrCreate(sessionId);
  state.historyLoadingMore = loading;
  notify(state);
}

/** Append a user message to a session. */
export function appendUserMessage(sessionId: string, msg: ChatMessage) {
  const state = getOrCreate(sessionId);
  state.messages = [...state.messages, msg];
  notify(state);
}

/**
 * Truncate all messages from messageId (inclusive) onwards, replacing that
 * message's content with newContent. Also aborts any in-flight stream.
 * Returns true if the message was found, false otherwise.
 */
export function truncateAndReplaceUserMessage(
  sessionId: string,
  messageId: string,
  newContent: string,
): boolean {
  const state = getOrCreate(sessionId);
  const idx = state.messages.findIndex((m) => m.id === messageId);
  if (idx < 0) return false;

  // Abort any in-flight stream before rewriting history
  state.abortController?.abort();
  state.abortController = null;

  const original = state.messages[idx];
  state.messages = [
    ...state.messages.slice(0, idx),
    { ...original, content: newContent, status: "done" as const },
  ];
  clearStreamingFlags(state);
  state.runUsage = null;
  state.streamMsg = "";
  state.streamId = "";
  state.streamBlockType = "";
  state.toolCallIdIndex = {};
  notify(state);
  return true;
}

/** Append a push (proactive/cron) assistant message to all active sessions. */
export function appendPushMessage(text: string) {
  const msg: ChatMessage = {
    id: generateId(),
    role: "assistant",
    content: text,
    timestamp: Date.now(),
  };
  for (const state of sessionStates.values()) {
    state.messages = [...state.messages, msg];
    notify(state);
  }
}

/** Clear all messages for a session, unless a turn is still in flight. */
export function clearMessages(sessionId: string) {
  const state = getOrCreate(sessionId);
  // Leaving a thread (agent switch, page change) must not seal a live turn:
  // the socket keeps streaming into this state and the UI needs it on return.
  if (state.isStreaming || isLiveSocketOpen(sessionId)) return;
  const alreadyEmpty =
    state.messages.length === 0 &&
    !state.isStreaming &&
    !state.historyHydrated &&
    state.historyNextOffset === 0 &&
    !state.historyHasMore;
  if (alreadyEmpty) return;
  state.messages = [];
  clearStreamingFlags(state);
  state.runUsage = null;
  state.streamMsg = "";
  state.streamId = "";
  state.streamBlockType = "";
  state.toolCallIdIndex = {};
  state.historyHasMore = false;
  state.historyNextOffset = 0;
  state.historyLoadingMore = false;
  state.historyHydrated = false;
  notify(state);
}

function clearLiveSocket(sessionId: string, ws?: WebSocket): void {
  const live = liveSockets.get(sessionId);
  if (!live) return;
  if (ws && live.ws !== ws) return;
  liveSockets.delete(sessionId);
}

function sendCancelFrame(ws: WebSocket, threadId: string): void {
  if (ws.readyState !== WebSocket.OPEN) return;
  try {
    ws.send(JSON.stringify({ type: "cancel", thread_id: threadId }));
  } catch {
    // ignore
  }
}

function closeLiveSocket(
  sessionId: string,
  opts: { intentional: boolean; userCancelled?: boolean },
): void {
  const live = liveSockets.get(sessionId);
  if (!live) return;
  live.intentionalClose = opts.intentional;
  if (opts.userCancelled) {
    live.userCancelled = true;
  }
  try {
    live.ws.close();
  } catch {
    // ignore
  }
  clearLiveSocket(sessionId);
}

/** Cancel any in-flight stream for a session (user stop). */
export function cancelStream(sessionId: string) {
  const state = sessionStates.get(sessionId);
  if (!state) return;
  const live = liveSockets.get(sessionId);
  if (live) {
    live.intentionalClose = true;
    live.userCancelled = true;
    sendCancelFrame(live.ws, live.threadId || sessionId);
  }
  const hadAbort = Boolean(state.abortController);
  const hadStreaming = state.isStreaming;
  const hadStreamingMsgs = state.messages.some((m) => m.status === "streaming");
  state.abortController?.abort();
  state.abortController = null;
  clearStreamingFlags(state);
  clearStreamActivity(sessionId);
  pendingResumeBySession.delete(sessionId);
  state.runUsage = null;
  if (hadStreamingMsgs) {
    state.messages = state.messages.map((m) =>
      m.status === "streaming" ? { ...m, status: "done" as const } : m,
    );
  }
  if (hadAbort || hadStreaming || hadStreamingMsgs) {
    notify(state);
  }
}

/** Remove a session from the cache entirely. */
export function removeSession(sessionId: string) {
  const state = sessionStates.get(sessionId);
  if (state) {
    state.abortController?.abort();
    sessionStates.delete(sessionId);
  }
  pendingResumeBySession.delete(sessionId);
  clearStreamActivity(sessionId);
  clearStreamWatchdog(sessionId);
  closeLiveSocket(sessionId, { intentional: true, userCancelled: true });
}

/** Rename a cached session's key (e.g. temp id → real UUID).
 *  Keeps the old key as an alias so that components still subscribed
 *  to the old id continue to receive updates until they remount.   */
export function renameSessionKey(oldId: string, newId: string) {
  const state = sessionStates.get(oldId);
  if (state && oldId !== newId) {
    // Both keys point to the same state object, so subscribers on
    // either key see the same messages / streaming status.
    sessionStates.set(newId, state);
    // Move live socket + resume bookkeeping to the canonical thread id so
    // loadHistory / attachThread for *newId* still see the open stream.
    const live = liveSockets.get(oldId);
    if (live) {
      liveSockets.delete(oldId);
      liveSockets.set(newId, live);
    }
    const pending = pendingResumeBySession.get(oldId);
    if (pending) {
      pendingResumeBySession.delete(oldId);
      pendingResumeBySession.set(newId, pending);
    }
    const activity = streamActivityAt.get(oldId);
    if (activity != null) {
      streamActivityAt.delete(oldId);
      streamActivityAt.set(newId, activity);
    }
    const wd = streamWatchdogs.get(oldId);
    if (wd != null) {
      streamWatchdogs.delete(oldId);
      streamWatchdogs.set(newId, wd);
    }
    if (focusedChatSessionId === oldId) {
      focusedChatSessionId = newId;
    }
    // Notify listeners so that components subscribed under the new key
    // (after a navigate) immediately see the existing messages.
    notify(state);
    // Don't delete oldId — the current component may still be
    // subscribed to it.  It will be cleaned up when the component
    // remounts with the new id.
  }
}

/**
 * Look up the store key that holds data for a given session ID.
 * Because temporary IDs get aliased to real UUIDs via renameSessionKey,
 * a component mounting with a UUID might find data under the old temp key.
 * This helper returns the canonical key (whichever one has data).
 */
export function resolveSessionKey(sessionId: string): string {
  // Direct match — most common path
  if (sessionStates.has(sessionId)) return sessionId;
  // Reverse lookup: another key might point to data whose listeners
  // are also registered under sessionId (same object reference).
  // But since renameSessionKey sets both keys to the same state object,
  // the direct lookup above should cover it.
  return sessionId;
}

/** Debug: dump all session keys and their message counts (noop in production). */
export function debugDump() {
  // Intentionally silent in production
}

// ── Harness chunk → state transitions ─────────────────────────────────────

function updateContextUsageFromChunk(
  state: SessionStreamState,
  chunk: { data: unknown },
): void {
  const data = chunk.data;
  if (!data || typeof data !== "object" || Array.isArray(data)) return;
  const messages = (data as { messages?: unknown[] }).messages;
  if (!Array.isArray(messages) || messages.length === 0) return;

  const last = messages[messages.length - 1] as Record<string, unknown>;
  const usageMeta = last.usage_metadata;
  if (!usageMeta || typeof usageMeta !== "object" || Array.isArray(usageMeta))
    return;

  const meta = usageMeta as Record<string, unknown>;
  const input =
    typeof meta.input_tokens === "number"
      ? meta.input_tokens
      : typeof meta.prompt_tokens === "number"
      ? meta.prompt_tokens
      : null;
  if (input === null || input <= 0) return;

  state.contextUsage = { input_tokens: input };
}

function findLastToolMessageIndex(state: SessionStreamState): number {
  for (let i = state.messages.length - 1; i >= 0; i--) {
    const m = state.messages[i];
    if (m.role === "assistant" && m.toolData) return i;
  }
  return -1;
}

function handleHarnessChunk(
  state: SessionStreamState,
  chunk: HarnessChunk,
  sessionId?: string,
): void {
  if (sessionId && state.isStreaming) {
    touchStreamActivity(sessionId);
  }
  switch (chunk.type) {
    case "token":
      appendStreamingToken(state, chunk.content);
      break;
    case "reasoning":
      appendStreamingReasoning(state, chunk.content);
      break;
    case "tool_call_chunk":
      upsertToolCall(state, chunk, sessionId);
      break;
    case "tool_result":
      closeToolCall(state, chunk.messages, sessionId);
      break;
    case "done":
      finalizeStreamingMessages(state);
      break;
    case "error":
      appendErrorBubble(state, chunk.message);
      break;
    case "hitl_required":
      handleHitlRequired(state, chunk.request);
      break;
    case "slash_action":
      emitSlashAction({
        action: chunk.action,
        agent_id: chunk.agent_id,
        sessionId,
      });
      break;
    case "attachment": {
      const url = typeof chunk.url === "string" ? chunk.url : "";
      const previewUrl =
        typeof chunk.preview_url === "string" ? chunk.preview_url : url;
      const b64 = typeof chunk.data === "string" ? chunk.data : "";
      const mime =
        typeof chunk.mime_type === "string"
          ? chunk.mime_type
          : "application/octet-stream";
      const displayUrl =
        previewUrl || (b64 ? `data:${mime};base64,${b64}` : "");
      if (!displayUrl) break;
      const kindRaw = typeof chunk.kind === "string" ? chunk.kind : "file";
      const toolIdx = findLastToolMessageIndex(state);
      const lastIdx = state.messages.length - 1;
      const last = lastIdx >= 0 ? state.messages[lastIdx] : null;
      const targetIdx =
        toolIdx >= 0
          ? toolIdx
          : last && last.role === "assistant"
          ? lastIdx
          : -1;
      const attachment = {
        url: displayUrl,
        kind: (kindRaw === "image" ? "image" : "file") as "image" | "file",
        filename:
          typeof chunk.filename === "string" ? chunk.filename : undefined,
        mediaType: mime !== "application/octet-stream" ? mime : undefined,
      };
      if (targetIdx >= 0) {
        const target = state.messages[targetIdx];
        const attachments = [...(target.attachments || []), attachment];
        state.messages = [
          ...state.messages.slice(0, targetIdx),
          { ...target, attachments },
          ...state.messages.slice(targetIdx + 1),
        ];
      } else {
        state.messages = [
          ...state.messages,
          {
            id: generateId(),
            role: "assistant",
            content: "",
            attachments: [attachment],
            status: "streaming",
            timestamp: Date.now(),
          },
        ];
      }
      break;
    }
    case "state_update":
    case "state_snapshot":
      updateContextUsageFromChunk(state, chunk);
      break;
    case "custom":
      // Debug-only — phase 15 will add a debug toggle that surfaces these.
      break;
  }
  notify(state);
}

/** Seal all streaming assistants before opening a new bubble (avoids multi-caret). */
function sealPriorStreamingAssistants(state: SessionStreamState): void {
  const next = sealPriorStreamingAssistantsMessages(state.messages);
  if (next !== state.messages) state.messages = next;
}

/** Append a token fragment to the last streaming assistant text bubble,
 *  starting a new bubble if the last message is something else. */
function appendStreamingToken(
  state: SessionStreamState,
  content: string,
): void {
  if (!content) return;
  const lastIdx = state.messages.length - 1;
  const last = lastIdx >= 0 ? state.messages[lastIdx] : null;
  if (
    last &&
    last.role === "assistant" &&
    last.status === "streaming" &&
    !last.toolData
  ) {
    const nextContent = (last.content || "") + content;
    if (last.contentBlocks && last.contentBlocks.length > 0) {
      const blocks = [...last.contentBlocks];
      const lastBlock = blocks[blocks.length - 1];
      if (lastBlock.type === "text") {
        blocks[blocks.length - 1] = {
          ...lastBlock,
          content: lastBlock.content + content,
        };
      } else {
        blocks.push({ type: "text", content });
      }
      state.messages = [
        ...state.messages.slice(0, lastIdx),
        { ...last, content: nextContent, contentBlocks: blocks },
      ];
      return;
    }
    state.messages = [
      ...state.messages.slice(0, lastIdx),
      { ...last, content: nextContent },
    ];
    return;
  }
  sealPriorStreamingAssistants(state);
  state.streamId = generateId();
  state.messages = [
    ...state.messages,
    {
      id: state.streamId,
      role: "assistant",
      content,
      status: "streaming",
      timestamp: Date.now(),
    },
  ];
}

/** Append a reasoning fragment as a thinking content block on the last
 *  streaming bubble (creating one if needed). Renderers that recognise
 *  contentBlocks will show it in a collapsible thinking panel. */
function appendStreamingReasoning(
  state: SessionStreamState,
  content: string,
): void {
  if (!content) return;
  const lastIdx = state.messages.length - 1;
  const last = lastIdx >= 0 ? state.messages[lastIdx] : null;
  if (
    last &&
    last.role === "assistant" &&
    last.status === "streaming" &&
    !last.toolData
  ) {
    const blocks = last.contentBlocks ? [...last.contentBlocks] : [];
    if (blocks.length > 0 && blocks[blocks.length - 1].type === "thinking") {
      const tail = blocks[blocks.length - 1];
      blocks[blocks.length - 1] = { ...tail, content: tail.content + content };
    } else {
      blocks.push({ type: "thinking", content });
    }
    state.messages = [
      ...state.messages.slice(0, lastIdx),
      { ...last, contentBlocks: blocks },
    ];
    return;
  }
  sealPriorStreamingAssistants(state);
  const id = generateId();
  state.streamId = id;
  state.messages = [
    ...state.messages,
    {
      id,
      role: "assistant",
      content: "",
      contentBlocks: [{ type: "thinking", content }],
      status: "streaming",
      timestamp: Date.now(),
    },
  ];
}

/** Start or update a tool-call bubble. Prefer harness ``id`` over ``index`` so
 *  parallel tool calls do not share name/args. */
function toolIndexKey(index: number | undefined): string {
  return `idx-${index ?? 0}`;
}

function resolveToolMessageId(
  state: SessionStreamState,
  chunk: ToolCallChunk,
): string | undefined {
  const id = chunk.id?.trim() || undefined;
  if (id) {
    const byId = state.toolCallIdIndex[id];
    if (byId) return byId;
  }

  const indexKey = toolIndexKey(chunk.index);
  const byIndex = state.toolCallIdIndex[indexKey];
  if (!byIndex) return undefined;

  if (id) {
    const existing = state.messages.find((m) => m.id === byIndex);
    const bound = existing?.toolData?.callId;
    if (bound && bound !== id && !bound.startsWith("idx-")) {
      return undefined;
    }
  }
  return byIndex;
}

function registerToolCallKeys(
  state: SessionStreamState,
  msgId: string,
  chunk: ToolCallChunk,
): void {
  const id = chunk.id?.trim() || undefined;
  const indexKey = toolIndexKey(chunk.index);
  state.toolCallIdIndex[indexKey] = msgId;
  if (id) state.toolCallIdIndex[id] = msgId;
}

function unregisterToolCallKeys(
  state: SessionStreamState,
  msgId: string,
): void {
  for (const [key, value] of Object.entries(state.toolCallIdIndex)) {
    if (value === msgId) delete state.toolCallIdIndex[key];
  }
}

function extractToolCallIdFromResult(messages: unknown[]): string | undefined {
  for (const raw of messages) {
    if (!raw || typeof raw !== "object") continue;
    const obj = raw as Record<string, unknown>;
    const tid = obj.tool_call_id ?? obj.toolCallId;
    if (typeof tid === "string" && tid.trim()) return tid.trim();
  }
  return undefined;
}

function upsertToolCall(
  state: SessionStreamState,
  chunk: ToolCallChunk,
  sessionId?: string,
): void {
  const id = chunk.id?.trim() || undefined;
  const indexKey = toolIndexKey(chunk.index);
  const callId = id ?? indexKey;
  const existingMsgId = resolveToolMessageId(state, chunk);
  if (existingMsgId) {
    const idx = state.messages.findIndex((m) => m.id === existingMsgId);
    if (idx >= 0) {
      const m = state.messages[idx];
      const prevArgs = m.toolData?.arguments ?? "";
      const nextArgs = prevArgs + (chunk.args ?? "");
      const nextName = chunk.name || m.toolData?.name;
      const nextDisplay = chunk.display_name || m.toolData?.displayName;
      const nextCallId =
        m.toolData?.callId?.startsWith("idx-") && id
          ? id
          : m.toolData?.callId ?? callId;
      state.messages = [
        ...state.messages.slice(0, idx),
        {
          ...m,
          toolData: {
            ...(m.toolData ?? {}),
            name: nextName,
            displayName: nextDisplay,
            callId: nextCallId,
            arguments: nextArgs,
          },
        },
        ...state.messages.slice(idx + 1),
      ];
      registerToolCallKeys(state, existingMsgId, chunk);
    }
    return;
  }
  sealPriorStreamingAssistants(state);
  const msgId = generateId();
  registerToolCallKeys(state, msgId, chunk);
  state.messages = [
    ...state.messages,
    {
      id: msgId,
      role: "assistant",
      content: "",
      toolData: {
        name: chunk.name,
        displayName: chunk.display_name,
        callId,
        arguments: chunk.args ?? "",
      },
      status: "streaming",
      timestamp: Date.now(),
    },
  ];
  emitToolEvent({
    kind: "toolStart",
    sessionId: sessionId ?? "",
    toolName: chunk.name ?? "",
    toolId: callId,
  });
}

/** Close the tool bubble that matches ``tool_call_id`` in the result, or the
 *  most recently opened streaming tool bubble as a fallback. */
function closeToolCall(
  state: SessionStreamState,
  messages: unknown[],
  sessionId?: string,
): void {
  const toolCallId = extractToolCallIdFromResult(messages);
  let toolIdx = -1;

  if (toolCallId) {
    const mapped = state.toolCallIdIndex[toolCallId];
    if (mapped) {
      toolIdx = state.messages.findIndex((m) => m.id === mapped);
    }
    if (toolIdx < 0) {
      for (let i = state.messages.length - 1; i >= 0; i--) {
        const m = state.messages[i];
        if (
          m.role === "assistant" &&
          m.toolData?.callId === toolCallId &&
          m.status === "streaming"
        ) {
          toolIdx = i;
          break;
        }
      }
    }
  }

  if (toolIdx < 0) {
    for (let i = state.messages.length - 1; i >= 0; i--) {
      const m = state.messages[i];
      if (m.role === "assistant" && m.toolData && m.status === "streaming") {
        toolIdx = i;
        break;
      }
    }
  }
  if (toolIdx < 0) return;
  const target = state.messages[toolIdx];
  let output = "";
  for (const raw of messages) {
    if (raw && typeof raw === "object") {
      const obj = raw as Record<string, unknown>;
      const content = obj.content;
      if (Array.isArray(content)) {
        const hasMedia = content.some(
          (part) =>
            part &&
            typeof part === "object" &&
            ["image", "file", "audio", "video"].includes(
              String((part as Record<string, unknown>).type || ""),
            ),
        );
        if (hasMedia) {
          output = JSON.stringify(content);
          break;
        }
        const textParts: string[] = [];
        for (const part of content) {
          if (
            part &&
            typeof part === "object" &&
            typeof (part as Record<string, unknown>).text === "string"
          ) {
            textParts.push(String((part as Record<string, unknown>).text));
          }
        }
        if (textParts.length > 0) {
          output = textParts.join("\n");
          break;
        }
      }
      if (content && typeof content === "object" && !Array.isArray(content)) {
        const part = content as Record<string, unknown>;
        if (
          ["image", "file", "audio", "video"].includes(String(part.type || ""))
        ) {
          output = JSON.stringify(content);
          break;
        }
      }
      if (typeof content === "string" && content) {
        const stripped = content.trim();
        if (stripped.startsWith("{") || stripped.startsWith("[")) {
          try {
            const parsed = JSON.parse(stripped);
            const blocks = Array.isArray(parsed)
              ? parsed
              : parsed && typeof parsed === "object"
              ? [parsed]
              : [];
            const hasMedia = blocks.some(
              (part) =>
                part &&
                typeof part === "object" &&
                ["image", "file", "audio", "video"].includes(
                  String((part as Record<string, unknown>).type || ""),
                ),
            );
            if (hasMedia) {
              output = stripped;
              break;
            }
            if (blocks.length > 0) {
              output = stripped;
              break;
            }
          } catch {
            // fall through
          }
        }
        output = content;
        break;
      }
      if (Array.isArray(content)) {
        for (const part of content) {
          if (
            part &&
            typeof part === "object" &&
            typeof (part as Record<string, unknown>).text === "string"
          ) {
            output = String((part as Record<string, unknown>).text);
            break;
          }
        }
        if (output) break;
      }
    }
  }
  state.messages = [
    ...state.messages.slice(0, toolIdx),
    {
      ...target,
      status: "done",
      toolData: {
        ...(target.toolData ?? {}),
        output,
      },
    },
    ...state.messages.slice(toolIdx + 1),
  ];
  unregisterToolCallKeys(state, target.id);
  emitToolEvent({
    kind: "toolDone",
    sessionId: sessionId ?? "",
    toolName: target.toolData?.name ?? "",
    toolId: target.toolData?.callId ?? "",
  });
}

/** Mark every still-streaming assistant bubble as done. */
function finalizeStreamingMessages(state: SessionStreamState): void {
  state.messages = state.messages.map((m) => {
    if (m.status !== "streaming") return m;
    // ModelRetryMiddleware may surface failures as assistant text instead of
    // type=error — promote those to an error bubble so users get guidance + retry.
    if (
      m.role === "assistant" &&
      !m.toolData &&
      typeof m.content === "string" &&
      isChatStreamError(m.content)
    ) {
      return {
        ...m,
        status: "error" as const,
        errorInfo: { code: "stream_error", source: "model_retry" },
      };
    }
    return { ...m, status: "done" as const };
  });
  state.streamMsg = "";
  state.streamId = "";
  state.streamBlockType = "";
}

function parseHitlRequest(raw: Record<string, unknown>) {
  const requests = Array.isArray(raw.action_requests)
    ? raw.action_requests
    : [];
  const action_requests = requests
    .filter((item) => item && typeof item === "object")
    .map((item) => {
      const row = item as Record<string, unknown>;
      return {
        name: typeof row.name === "string" ? row.name : "tool",
        args:
          row.args && typeof row.args === "object"
            ? (row.args as Record<string, unknown>)
            : {},
        description:
          typeof row.description === "string" ? row.description : undefined,
      };
    });
  const review_configs = Array.isArray(raw.review_configs)
    ? raw.review_configs
        .filter((item) => item && typeof item === "object")
        .map(
          (item) =>
            item as {
              action_name: string;
              allowed_decisions: string[];
            },
        )
    : undefined;
  return { action_requests, review_configs, status: "pending" as const };
}

function resolveHitlPending(
  state: SessionStreamState,
  status: "approved" | "rejected",
): void {
  state.messages = state.messages.map((m) =>
    m.hitlData ? { ...m, hitlData: { ...m.hitlData, status } } : m,
  );
}

function handleHitlRequired(
  state: SessionStreamState,
  request: Record<string, unknown>,
): void {
  finalizeStreamingMessages(state);
  clearStreamingFlags(state);
  state.messages = [
    ...state.messages,
    {
      id: generateId(),
      role: "assistant",
      content: "",
      hitlData: parseHitlRequest(request),
      status: "done",
      timestamp: Date.now(),
    },
  ];
}

/** Append an assistant error bubble — used for backend-emitted error
 *  chunks and HTTP-layer failures. */
function appendErrorBubble(state: SessionStreamState, message: string): void {
  state.messages = [
    ...state.messages,
    {
      id: generateId(),
      role: "assistant",
      content: message,
      errorInfo: { code: "stream_error", source: "frontend_stream" },
      status: "error",
      timestamp: Date.now(),
    },
  ];
}

// ── Live WebSocket (send + weak stream resume) ─────────────────────────────

/**
 * After history load (or reconnect): subscribe to *threadId* and continue an
 * in-flight turn when the server reports ``turn_status.active``.
 *
 * @param resumeAttempt Internal counter for auto-reconnect after drop (do not
 *   pass from call sites except recursive re-attach).
 */
export async function attachThread(
  sessionId: string,
  agentId: string,
  threadId: string,
  onStreamEnd?: () => void,
  resumeAttempt = 0,
  opts?: { afterUnexpectedDrop?: boolean },
): Promise<void> {
  if (!agentId || !threadId || threadId === "__empty__") return;

  const existing = liveSockets.get(sessionId);
  if (
    existing &&
    existing.agentId === agentId &&
    existing.threadId === threadId &&
    existing.ws.readyState === WebSocket.OPEN
  ) {
    // Already bound — do not re-send subscribe (avoids turn_status churn).
    return;
  }

  if (existing) {
    // Rebind only — do not send cancel / do not seal streaming bubbles.
    closeLiveSocket(sessionId, { intentional: true });
  }

  const state = getOrCreate(sessionId);
  const ws = tryOpenDashboardWs(agentId);
  if (!ws) {
    if (state.isStreaming) {
      clearStreamingFlags(state);
      clearStreamActivity(sessionId);
      notify(state);
    }
    return;
  }

  const live: LiveSocket = {
    ws,
    agentId,
    threadId,
    intentionalClose: false,
    userCancelled: false,
  };
  liveSockets.set(sessionId, live);

  // Do not clobber an in-flight sendTurn controller unless we need cancel
  // affinity for this resume socket.
  const controller = new AbortController();
  const previousController = state.abortController;
  state.abortController = controller;

  let finished = false;
  const finish = () => {
    if (finished) return;
    finished = true;
    clearStreamingFlags(state);
    clearStreamActivity(sessionId);
    pendingResumeBySession.delete(sessionId);
    if (state.abortController === controller) {
      state.abortController = null;
    }
    state.streamMsg = "";
    state.streamId = "";
    state.streamBlockType = "";
    sealInFlightAssistantMessages(state);
    notify(state);
    emitStreamEvent({ kind: "streamEnd", sessionId });
    onStreamEnd?.();
  };

  await new Promise<void>((resolve) => {
    let opened = false;
    const settleOpen = () => {
      if (opened) return;
      opened = true;
      resolve();
    };

    const onAbort = () => {
      live.intentionalClose = true;
      live.userCancelled = true;
      sendCancelFrame(ws, threadId);
      try {
        ws.close();
      } catch {
        // ignore
      }
      finish();
    };
    controller.signal.addEventListener("abort", onAbort, { once: true });

    ws.onopen = () => {
      touchStreamActivity(sessionId);
      try {
        ws.send(JSON.stringify({ type: "subscribe", thread_id: threadId }));
      } catch {
        // ignore
      }
      settleOpen();
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(String(event.data)) as Record<string, unknown>;
        if (!data || typeof data !== "object") return;

        if (data.type === "turn_status") {
          if (turnStatusAction(Boolean(data.active)) === "expect_stream") {
            if (!state.isStreaming) {
              beginStream(state, sessionId);
              notify(state);
              emitStreamEvent({ kind: "streamStart", sessionId });
            } else {
              touchStreamActivity(sessionId);
            }
            if (
              shouldEmitStreamResumeNotice({
                resumeAttempt:
                  opts?.afterUnexpectedDrop && resumeAttempt === 0
                    ? 1
                    : resumeAttempt,
                turnActive: true,
              })
            ) {
              emitStreamEvent({ kind: "streamResume", sessionId });
            }
          } else {
            // Idle on server — clear any sticky local streaming from a race,
            // then drop the probe socket so scroll/history UX is unaffected.
            live.intentionalClose = true;
            controller.signal.removeEventListener("abort", onAbort);
            try {
              ws.close();
            } catch {
              // ignore
            }
            clearLiveSocket(sessionId, ws);
            if (state.isStreaming) {
              finish();
            } else if (state.abortController === controller) {
              state.abortController = previousController;
            }
          }
          return;
        }

        if (data.type === "pong") return;

        handleHarnessChunk(state, data as unknown as HarnessChunk, sessionId);
        if (
          data.type === "done" ||
          data.type === "error" ||
          data.type === "hitl_required"
        ) {
          live.intentionalClose = true;
          controller.signal.removeEventListener("abort", onAbort);
          try {
            ws.close();
          } catch {
            // ignore
          }
          clearLiveSocket(sessionId, ws);
          finish();
        }
      } catch {
        // ignore malformed frames
      }
    };

    ws.onerror = () => {
      settleOpen();
    };

    ws.onclose = () => {
      controller.signal.removeEventListener("abort", onAbort);
      const wasIntentional = live.intentionalClose;
      const userCancelled = live.userCancelled;
      const stillStreaming = state.isStreaming;
      clearLiveSocket(sessionId, ws);
      settleOpen();
      // Socket replaced by a newer live for this session without user cancel —
      // keep sticky isStreaming so thread switch / rebind does not seal bubbles.
      if (wasIntentional && !userCancelled && stillStreaming) {
        if (state.abortController === controller) {
          state.abortController = previousController;
        }
        if (isLiveSocketOpen(sessionId)) {
          return;
        }
        // No replacement yet (edge race) — leave streaming, allow focus rebind.
        if (!pendingResumeBySession.has(sessionId)) {
          pendingResumeBySession.set(sessionId, {
            agentId,
            threadId,
            onStreamEnd,
            resumeAttempt: resumeAttempt + 1,
            opts: opts ?? { afterUnexpectedDrop: true },
          });
        }
        return;
      }
      if (stillStreaming && !wasIntentional) {
        // Keep grace window for sticky-seal watchdog while re-attaching.
        touchStreamActivity(sessionId);
      }
      const focused = isSessionFocused(sessionId);
      if (
        shouldResumeStreamAfterClose({
          intentionalClose: wasIntentional,
          isStreaming: stillStreaming,
          threadId,
          attempt: resumeAttempt,
          maxAttempts: MAX_STREAM_RESUME_ATTEMPTS,
          sessionFocused: focused,
        })
      ) {
        setTimeout(() => {
          void attachThread(
            sessionId,
            agentId,
            threadId,
            onStreamEnd,
            resumeAttempt + 1,
            opts,
          );
        }, 400);
      } else if (
        stillStreaming &&
        !wasIntentional &&
        !focused &&
        resumeAttempt < MAX_STREAM_RESUME_ATTEMPTS
      ) {
        // Background tab: remember rebind when the user returns.
        pendingResumeBySession.set(sessionId, {
          agentId,
          threadId,
          onStreamEnd,
          resumeAttempt: resumeAttempt + 1,
          opts,
        });
        clearStreamWatchdog(sessionId);
      } else if (!wasIntentional && stillStreaming) {
        // Exhausted retries or failed open — do not leave sticky isStreaming.
        finish();
      } else if (state.abortController === controller) {
        state.abortController = previousController;
      }
    };
  });
}

// ── Send a message via Dashboard WebSocket (/api/agents/{id}/chat/ws) ────────
async function sendTurnWebSocket(
  sessionId: string,
  agentId: string,
  sessionKey: string,
  text: string,
  messageContent: string | Array<Record<string, unknown>>,
  controller: AbortController,
  finish: () => void,
  modelRef?: string | null,
  threadId?: string | null,
  mcpServers?: string[] | null,
  skills?: string[] | null,
  targetAgentIds?: string[] | null,
  onStreamEnd?: () => void,
): Promise<boolean> {
  const state = getOrCreate(sessionId);
  const resolvedThreadId = (threadId || sessionId).trim();

  if (liveSockets.has(sessionId)) {
    // Replace prior socket for this session without cancelling the server turn.
    closeLiveSocket(sessionId, { intentional: true });
  }

  return new Promise((resolve) => {
    const ws = tryOpenDashboardWs(agentId);
    if (!ws) {
      resolve(false);
      return;
    }

    const live: LiveSocket = {
      ws,
      agentId,
      threadId: resolvedThreadId,
      intentionalClose: false,
      userCancelled: false,
    };
    liveSockets.set(sessionId, live);

    let settled = false;
    const settle = (ok: boolean) => {
      if (settled) return;
      settled = true;
      resolve(ok);
    };

    let openedForTurn = false;
    const onAbort = () => {
      live.intentionalClose = true;
      live.userCancelled = true;
      sendCancelFrame(ws, resolvedThreadId);
      try {
        ws.close();
      } catch {
        // ignore
      }
      finish();
      settle(true);
    };
    controller.signal.addEventListener("abort", onAbort, { once: true });

    ws.onopen = () => {
      openedForTurn = true;
      const payload: Record<string, unknown> = {
        type: "user_turn",
        text: typeof messageContent === "string" ? messageContent : text,
        session_key: sessionKey,
        messages: [
          {
            role: "user",
            content: messageContent,
          },
        ],
      };
      if (threadId) payload.thread_id = threadId;
      if (modelRef) payload.model = modelRef;
      // Always send the array (including []) so the server can honor Dashboard
      // opt-out of default_open connectors for this turn.
      if (mcpServers !== undefined && mcpServers !== null) {
        payload.mcp_servers = mcpServers;
      }
      if (skills && skills.length > 0) payload.skills = skills;
      if (targetAgentIds && targetAgentIds.length > 0) {
        payload.target_agent_ids = targetAgentIds;
      }
      ws.send(JSON.stringify(payload));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(String(event.data)) as HarnessChunk;
        if (!data || typeof data !== "object") return;
        if ((data as { type?: string }).type === "turn_status") return;
        handleHarnessChunk(state, data, sessionId);
        if (
          data.type === "done" ||
          data.type === "error" ||
          data.type === "hitl_required"
        ) {
          live.intentionalClose = true;
          controller.signal.removeEventListener("abort", onAbort);
          try {
            ws.close();
          } catch {
            // ignore
          }
          clearLiveSocket(sessionId, ws);
          finish();
          settle(true);
        }
      } catch {
        // ignore malformed frames
      }
    };

    ws.onerror = () => {
      // Prefer onclose to decide resume vs fail — browsers almost always fire both.
    };

    ws.onclose = () => {
      const wasIntentional = live.intentionalClose;
      const userCancelled = live.userCancelled;
      // Capture before any finish() clears streaming flags.
      const focused = isSessionFocused(sessionId);
      clearLiveSocket(sessionId, ws);
      controller.signal.removeEventListener("abort", onAbort);

      // Failed to open (unit tests / offline) — seal without resume thrash.
      if (!openedForTurn && !userCancelled) {
        if (!settled) {
          finish();
          settle(true);
        }
        return;
      }

      const shouldResume = shouldResumeStreamAfterClose({
        intentionalClose: wasIntentional,
        isStreaming: state.isStreaming,
        threadId: resolvedThreadId,
        sessionFocused: focused,
      });

      if (shouldResume) {
        // Keep isStreaming + partial assistant bubble; re-subscribe for later chunks.
        // Do NOT finish() — that seals incomplete content and blocks free-scroll UX.
        touchStreamActivity(sessionId);
        if (!settled) settle(true);
        setTimeout(() => {
          void attachThread(
            sessionId,
            agentId,
            resolvedThreadId,
            onStreamEnd,
            0,
            {
              afterUnexpectedDrop: true,
            },
          );
        }, 400);
        return;
      }

      if (state.isStreaming && !wasIntentional && !focused) {
        touchStreamActivity(sessionId);
        pendingResumeBySession.set(sessionId, {
          agentId,
          threadId: resolvedThreadId,
          onStreamEnd,
          resumeAttempt: 1,
          opts: { afterUnexpectedDrop: true },
        });
        clearStreamWatchdog(sessionId);
        if (!settled) settle(true);
        return;
      }

      // Intentional socket *replace* (new live already bound) without user stop:
      // keep sticky isStreaming so rebind continues receiving chunks.
      if (wasIntentional && !userCancelled && state.isStreaming && !settled) {
        if (isLiveSocketOpen(sessionId)) {
          settle(true);
          return;
        }
      }

      if (!settled) {
        finish();
        settle(true);
      }
    };
  });
}

export async function sendTurn(
  sessionId: string,
  text: string,
  agentId: string,
  sessionKey: string,
  attachments?: ChatAttachment[],
  onStreamEnd?: () => void,
  modelRef?: string | null,
  threadId?: string | null,
  mcpServers?: string[] | null,
  skills?: string[] | null,
  targetAgentIds?: string[] | null,
): Promise<void> {
  const state = getOrCreate(sessionId);

  if (!agentId) {
    appendErrorBubble(state, "No agent selected. Pick one from the top bar.");
    clearStreamingFlags(state);
    clearStreamActivity(sessionId);
    notify(state);
    onStreamEnd?.();
    return;
  }

  // Abort any prior stream for this session.
  state.abortController?.abort();
  state.toolCallIdIndex = {};
  state.streamMsg = "";
  state.streamId = "";
  state.streamBlockType = "";
  beginStream(state, sessionId);
  state.runUsage = null;
  notify(state);

  emitStreamEvent({ kind: "streamStart", sessionId });

  const controller = new AbortController();
  state.abortController = controller;

  const messageContent = buildUserMessageContent(text, attachments);

  const finish = () => {
    clearStreamingFlags(state);
    clearStreamActivity(sessionId);
    pendingResumeBySession.delete(sessionId);
    state.abortController = null;
    state.streamMsg = "";
    state.streamId = "";
    state.streamBlockType = "";
    sealInFlightAssistantMessages(state);
    notify(state);
    emitStreamEvent({ kind: "streamEnd", sessionId });
    onStreamEnd?.();
  };

  const wsOk = await sendTurnWebSocket(
    sessionId,
    agentId,
    sessionKey,
    text,
    messageContent,
    controller,
    finish,
    modelRef,
    threadId,
    mcpServers,
    skills,
    targetAgentIds,
    onStreamEnd,
  );
  if (!wsOk) {
    state.messages = [
      ...state.messages,
      {
        id: generateId(),
        role: "assistant",
        content: "WebSocket connection failed. Check network or server logs.",
        errorInfo: { code: "ws_error", source: "frontend_stream" },
        status: "error",
        timestamp: Date.now(),
      },
    ];
    finish();
  }
}

async function consumeSseResponse(
  state: SessionStreamState,
  sessionId: string,
  res: Response,
  controller: AbortController,
  finish: () => void,
): Promise<void> {
  const reader = res.body?.getReader();
  if (!reader) {
    finish();
    return;
  }

  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nlIdx: number;
    while ((nlIdx = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, nlIdx).replace(/\r$/, "");
      buffer = buffer.slice(nlIdx + 1);
      if (!line) continue;
      const chunk = parseHarnessChunk(line);
      if (!chunk) continue;
      handleHarnessChunk(state, chunk, sessionId);
      if (
        chunk.type === "done" ||
        chunk.type === "error" ||
        chunk.type === "hitl_required"
      ) {
        controller.abort();
        finish();
        return;
      }
    }
  }

  if (buffer.length > 0) {
    const chunk = parseHarnessChunk(buffer);
    if (chunk) handleHarnessChunk(state, chunk, sessionId);
  }

  finish();
}

export async function resumeHitl(
  sessionId: string,
  agentId: string,
  threadId: string,
  decisions: Array<{ type: string; message?: string }>,
): Promise<void> {
  const state = getOrCreate(sessionId);
  state.abortController?.abort();
  const hitlStatus = decisions.some((d) => d.type === "reject")
    ? "rejected"
    : "approved";
  resolveHitlPending(state, hitlStatus);
  beginStream(state, sessionId);
  notify(state);
  emitStreamEvent({ kind: "streamStart", sessionId });

  const controller = new AbortController();
  state.abortController = controller;

  const headers: HeadersInit = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  };
  const token = getAuthToken();
  if (token) {
    (headers as Record<string, string>).Authorization = `Bearer ${token}`;
  }

  const finish = () => {
    clearStreamingFlags(state);
    clearStreamActivity(sessionId);
    pendingResumeBySession.delete(sessionId);
    state.abortController = null;
    state.streamMsg = "";
    state.streamId = "";
    state.streamBlockType = "";
    sealInFlightAssistantMessages(state);
    notify(state);
    emitStreamEvent({ kind: "streamEnd", sessionId });
  };

  try {
    const res = await fetch(getApiUrl(`/agents/${agentId}/chat/hitl/resume`), {
      method: "POST",
      headers,
      body: JSON.stringify({ thread_id: threadId, decisions }),
      signal: controller.signal,
    });
    if (!res.ok) {
      appendErrorBubble(state, `HITL resume failed (${res.status})`);
      finish();
      return;
    }
    await consumeSseResponse(state, sessionId, res, controller, finish);
  } catch (err: unknown) {
    if ((err as Error).name === "AbortError") return;
    appendErrorBubble(state, (err as Error).message || "HITL resume error");
    finish();
  }
}
